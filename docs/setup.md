# Setup

This is what you need on your machine to bring Hiremesh up locally.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker Desktop (or compatible) | recent | Provides Docker Engine + Compose v2 |
| `make` | any | Wraps the common entry points |
| `git` | any | |
| Python | 3.13 | Only needed if you want a host-side dev venv (see [dev-workflow.md](./dev-workflow.md)) |
| `uv` | 0.11+ | Python package/venv manager. `brew install uv` |
| Node | 22+ | Only needed if you want to run `next dev` outside Docker |

You do **not** need Python or Node installed on the host to run the app — Docker handles everything. They're only needed for editor tooling, fast unit tests, and local dev servers.

## First boot

```bash
git clone <this repo>
cd hiremesh

cp infra/.env.example infra/.env
# Edit infra/.env:
#   - generate JWT_SECRET:  openssl rand -base64 48
#   - set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD

make up
```

`make up` will:
1. Build the `api`, `worker`, and `web` images.
2. Start postgres (with pgvector), redis, api, worker, web, and caddy.
3. The api container runs `alembic upgrade head` before starting uvicorn.
4. On first boot (when the `users` table is empty), the api creates an admin from the `BOOTSTRAP_ADMIN_*` env vars. Subsequent boots are no-ops.

When everything is healthy:

| URL | What it serves |
|---|---|
| `http://localhost/` | Next.js app (redirects `/` → `/dashboard`, gated by middleware) |
| `http://localhost/login` | Sign-in page |
| `http://localhost/api/health` | API health check (`{"status":"ok"}`) |
| `http://localhost/api/docs` | FastAPI auto-generated API docs |

Sign in with the bootstrap admin email/password from your `.env`. You'll be marked `must_change_password=true` so you should change it from the API at `POST /api/auth/me/password` (UI to follow in M1+).

## Environment variables

See [`infra/.env.example`](../infra/.env.example) — every variable is commented inline.

The two variables you must set before first boot are `JWT_SECRET` and the `BOOTSTRAP_ADMIN_*` trio. Everything else has dev-friendly defaults.

## Verifying the stack is healthy

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml ps
# expect: postgres + redis healthy; api/worker/web/caddy up
curl -s http://localhost/api/health
# {"status":"ok"}
curl -s -i -X POST http://localhost/api/auth/login \
  -H "content-type: application/json" \
  -d "{\"email\":\"$BOOTSTRAP_ADMIN_EMAIL\",\"password\":\"$BOOTSTRAP_ADMIN_PASSWORD\"}"
# 200 OK with a Set-Cookie: hiremesh_session=...
```

## Tearing down

```bash
make down            # stop & remove containers (data persists in volumes)
docker volume rm hiremesh_postgres_data   # nuke the database
```

## Troubleshooting

- **Caddy fails to bind port 80**: check `lsof -nP -iTCP:80 -sTCP:LISTEN` for a conflicting process on the host. On macOS, this is sometimes `httpd` or another container exposing port 80.
- **`alembic upgrade head` fails on api startup**: the postgres container may not be fully ready yet — compose's `service_healthy` should prevent this, but if it happens, `make down && make up`.
- **`make up` hangs without output**: a previous `docker compose` run may have left orphaned processes. `pkill -9 -f "docker compose"` and retry. If that doesn't help, restart Docker Desktop.
