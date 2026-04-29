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
#   - (LLM model env vars are optional; the stack runs in `fake` mode without keys)

make up
```

`make up` will:
1. Build the `api`, `worker`, and `web` images.
2. Start postgres (with pgvector), redis, api, worker, web, and caddy.
3. The api container runs `alembic upgrade head` before starting uvicorn.

There is **no env-based bootstrap admin** — fresh databases start empty. After `make up` completes, create the first admin via the CLI:

```bash
make admin-create EMAIL=you@example.com NAME="Your Name"
# (you'll be prompted for a password, echo off, min 12 chars)
```

This dropped the `BOOTSTRAP_ADMIN_*` env vars deliberately: storing a password in plaintext in `.env`, only honoured on first-empty-table boot, was a prod footgun. The CLI also lets you reset a forgotten password later (`make admin-set-password EMAIL=...`) and list current admins (`make admin-list`).

When everything is healthy:

| URL | What it serves |
|---|---|
| `http://localhost/` | Next.js app (redirects `/` → `/dashboard`, gated by middleware) |
| `http://localhost/login` | Sign-in page |
| `http://localhost/api/health` | API health check (`{"status":"ok"}`) |
| `http://localhost/api/docs` | FastAPI auto-generated API docs |

Sign in with the credentials you set via `make admin-create`. From the admin you can create other users from the in-app `/admin/users` page or `POST /api/users`.

## Environment variables

See [`infra/.env.example`](../infra/.env.example) — every variable is commented inline.

The only variable you **must** set before first boot is `JWT_SECRET`. Everything else has dev-friendly defaults.

To enable real AI features (resume parsing, semantic search, Ask), set the three LLM model env vars and a key. Each is independent — they default to `fake` so the stack runs end-to-end without any API key. See [`ops.md`](./ops.md#llm-model-configuration) for the full table; the short version:

```env
LLM_PARSE_MODEL=openrouter/openai/gpt-4o-mini
LLM_EMBED_MODEL=openrouter/openai/text-embedding-3-small
LLM_QA_MODEL=openrouter/openai/gpt-4o-mini
LLM_EMBED_DIM=1536          # must match the embed model's output dim
LLM_API_KEY=sk-or-v1-...    # OpenRouter, OpenAI, etc.
```

All three vars pass through `infra/docker-compose.yml`'s `&backend_env` block. Changes need `make up` (not just `restart`) to take effect, since adding/changing env-var passthroughs requires recreating the containers.

## Verifying the stack is healthy

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml ps
# expect: postgres + redis healthy; api/worker/web/caddy up
curl -s http://localhost/api/health
# {"status":"ok"}
curl -s -i -X POST http://localhost/api/auth/login \
  -H "content-type: application/json" \
  -d '{"email":"you@example.com","password":"the-password-you-set-via-cli"}'
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
