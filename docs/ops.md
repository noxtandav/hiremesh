# Ops

Day-2 concerns: backups, restoring from a dump, deploying to a VPS, basic health checks.

## Backups

### What we ship

A standalone shell script at [`infra/backups/pg_dump_to_s3.sh`](../infra/backups/pg_dump_to_s3.sh) that:

1. Runs `pg_dump --format=custom` against `DATABASE_URL`.
2. Pipes the output through `gzip`.
3. Uploads the dump to an S3-compatible bucket using the MinIO client (`mc`).
4. Prunes objects older than `RETENTION_DAYS` (default 30).

It is **not** part of the default `docker-compose.yml`. Backups want different schedules, retention, and credentials per deployment, so we keep them as a separate runnable.

### Required env

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Full Postgres URL, e.g. `postgres://hiremesh:hiremesh@postgres:5432/hiremesh` |
| `S3_ENDPOINT` | Bucket endpoint URL (e.g. `https://<account>.r2.cloudflarestorage.com`) |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | S3 credentials + bucket name |
| `BACKUP_PREFIX` | Optional, defaults to `hiremesh`. Object keys land at `<prefix>/<host>/<date>/...`. |
| `BACKUP_HOST_TAG` | Optional. Distinguishes multiple environments (e.g. `prod`, `staging`). |
| `RETENTION_DAYS` | Optional, default 30. Set 0 to disable pruning. |

### Run it once, manually

From a host that has `pg_dump` and `mc` installed:

```bash
DATABASE_URL='postgresql://hiremesh:hiremesh@localhost:5432/hiremesh' \
S3_ENDPOINT='https://<acct>.r2.cloudflarestorage.com' \
S3_ACCESS_KEY=... S3_SECRET_KEY=... S3_BUCKET=hiremesh-backups \
BACKUP_HOST_TAG=prod \
infra/backups/pg_dump_to_s3.sh
```

Or run it inside a one-shot container so you don't have to install `pg_dump`/`mc` locally:

```bash
docker run --rm \
  --network hiremesh_default \
  -v "$PWD/infra/backups:/scripts" \
  -e DATABASE_URL='postgresql://hiremesh:hiremesh@postgres:5432/hiremesh' \
  -e S3_ENDPOINT='http://minio:9000' \
  -e S3_ACCESS_KEY=minio -e S3_SECRET_KEY=minio12345 \
  -e S3_BUCKET=hiremesh -e BACKUP_HOST_TAG=dev \
  --entrypoint sh \
  postgres:16-alpine -c "apk add --no-cache mc && /scripts/pg_dump_to_s3.sh"
```

### Schedule it

Pick the option that matches your deploy:

**Host crontab** (simplest, runs on the VPS itself):
```cron
# Daily at 02:00 UTC
0 2 * * * cd /opt/hiremesh && env $(cat infra/.env.backup | xargs) infra/backups/pg_dump_to_s3.sh >> /var/log/hiremesh-backup.log 2>&1
```

**systemd timer** (cleaner journaling, recommended on Linux VPS):
- Create `/etc/systemd/system/hiremesh-backup.service` calling the script with `EnvironmentFile`.
- Pair with a `hiremesh-backup.timer` set to `OnCalendar=daily`.

**GitHub Actions on a schedule** (works if your DB is reachable from GitHub runners):
```yaml
on:
  schedule:
    - cron: "0 2 * * *"
```

### Restoring

```bash
# 1. download the dump
mc cp bk/hiremesh-backups/hiremesh/prod/2026-04-28/hiremesh-20260428T020001Z.dump.gz .
gunzip hiremesh-20260428T020001Z.dump.gz

# 2. point at the target DB and restore
PGPASSWORD=hiremesh pg_restore \
  --host=localhost --port=5432 --username=hiremesh --dbname=hiremesh \
  --clean --if-exists --no-owner --no-privileges \
  hiremesh-20260428T020001Z.dump
```

Notes on `--clean --if-exists`:
- `pg_restore` will drop existing objects before recreating them. For a true clean restore, drop and recreate the database first (`DROP DATABASE hiremesh; CREATE DATABASE hiremesh;`) and run without `--clean`.
- Restore on a fresh database, then run `alembic upgrade head` to reach the migration head if the dump was older.

### What's NOT backed up by this script

- **Object storage** (resumes in MinIO/R2). The dump only contains DB rows; resume blobs live separately. For production, set bucket-level versioning + cross-region replication on R2 — that's the right tool. (We may add an `mc mirror` companion script later.)
- **Redis state**. The Celery queue is ephemeral; nothing here needs backing up.

## Deploying to a VPS

Out of scope for this doc, but the high-level path is:

1. SSH to a fresh box; install Docker + Docker Compose.
2. `git clone` the repo to `/opt/hiremesh`.
3. `cp infra/.env.example infra/.env`; fill secrets, set `COOKIE_SECURE=true`.
4. Set `S3_ENDPOINT`, `S3_PUBLIC_ENDPOINT`, and bucket creds to point at R2 (not MinIO).
5. Configure Caddy for the real hostname — replace the `:80` block with `your-domain.com {}` and let Caddy auto-issue TLS.
6. `make up`.
7. Verify: `curl https://your-domain.com/api/health` returns ok.
8. Set up backups (above) and start watching `/admin/metrics`.

## Health and metrics

- `GET /api/health` — public, returns `{"status":"ok"}` once the API is alive.
- `GET /api/admin/metrics` — admin-cookie. Returns counts (candidates, jobs, embeddings, parse status), Celery queue depth, and the configured model ids.
- The frontend exposes the same numbers visually at `/admin/metrics`.

There is no Prometheus exposition format yet; the JSON endpoint is what dashboards should scrape. Adding `/metrics` in Prometheus format is straightforward when the time comes.

## Logs

Container logs are the source of truth:

```bash
docker compose -f infra/docker-compose.yml logs -f api worker
```

The audit log (`/admin/audit-log` or directly via `audit_log` table) is for **operational** events — logins, user mgmt, candidate mutations, reindex/reset. It's best-effort and intentionally not in the request critical path.
