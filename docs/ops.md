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

## Admin user management

There is no env-based bootstrap admin — fresh deployments start with an empty `users` table. Use the CLI shipped at `app/cli.py` against the running api container.

| Operation | Command |
|---|---|
| Create the first admin (or any other admin) | `make admin-create EMAIL=you@example.com NAME="Your Name"` |
| Reset a user's password (forgot password, lost MFA, etc.) | `make admin-set-password EMAIL=user@example.com` |
| List all current admins (sanity check / audit) | `make admin-list` |

All three prompt for the password interactively (echo off, min 12 chars). You can pass `--password ...` to skip the prompt — useful for CI/IaC, but the password lands in shell history, so prefer the prompt for ad-hoc work.

Behind the scenes each `make` target shells out to `docker compose exec api python -m app.cli admin <subcommand>`, which uses the same SQLAlchemy session and password hashing the running app uses. If you need to run it outside Docker (e.g. against a remote DB from your laptop), set `DATABASE_URL` and run `python -m app.cli ...` directly inside the backend venv.

`make admin-set-password` will also re-activate a deactivated user. To deactivate without resetting the password, use the in-app `/admin/users` page or `PATCH /api/users/{id}` directly.

## LLM model configuration

Three independent env vars cover the three LLM roles. Each defaults to `fake` (deterministic dev mode, no network calls). Set what you need in `infra/.env`:

| Env var | Used for | Notes |
|---|---|---|
| `LLM_PARSE_MODEL` | Resume parsing — extracts structured fields (name, email, skills, etc.) from text. | Cheap chat model is fine; `gpt-4o-mini` class. |
| `LLM_EMBED_MODEL` | Embeddings for the talent pool — drives semantic search and pool Ask. | Must be an embedding model (e.g. `text-embedding-3-small`, `voyage-3-large`). `LLM_EMBED_DIM` must match. |
| `LLM_QA_MODEL` | All four Q&A roles: per-candidate Ask synthesis, pool classifier, structured-query SQL gen, pool synthesis. | Anything Claude-Haiku-class or `gpt-4o-mini` works; `gpt-4o` / Claude Sonnet give noticeably better SQL gen and routing if you start hitting issues. |
| `LLM_API_KEY` | Optional override. If unset, LiteLLM picks the right provider env (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `COHERE_API_KEY`) by model prefix. | Use the per-provider envs when mixing providers across roles. |

All four pass through `infra/docker-compose.yml`'s `&backend_env` block, so changing them requires `make up` (or `docker compose up -d`) to recreate containers — `restart` alone keeps the old environment.

The `/admin/metrics` page surfaces the configured model ids so you can sanity-check what's actually live without exec'ing into the container.

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
