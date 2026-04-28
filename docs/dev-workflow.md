# Dev workflow

How the project is organized for day-to-day work, and how to get fast feedback without paying the full Docker boot cost on every change.

## Two execution paths

Python work runs in one of two places — pick whichever is faster for the task at hand. **Never against the host's system Python.**

| | Where | When to use it |
|---|---|---|
| **Docker (`make up`)** | inside the `api` and `worker` containers | DB-touching code, end-to-end testing, anything that needs Postgres / Redis / R2 |
| **Host venv (`backend/.venv`)** | a `uv`-managed venv pinned to the same `pyproject.toml` | unit tests, type checks, formatters, quick imports — anything that doesn't need external services |

The same lockfile drives both, so deps don't drift.

### Bootstrapping the host venv

```bash
make venv     # uv venv .venv --python 3.13 + uv pip install -e ".[dev]"
```

After that, your editor can point at `backend/.venv/bin/python` and you can run things directly:

```bash
cd backend
.venv/bin/pytest -q
.venv/bin/ruff check .
```

### Running things inside the api container

```bash
make api-sh                          # interactive shell
make migrate                         # alembic upgrade head
make makemigration m="add candidates"  # autogenerate a new revision
```

Frontend lives outside this split — it always runs via npm or Docker.

## Common Make targets

```
make help            # list everything
make up              # build and start the full stack
make down            # stop & remove containers (volumes persist)
make logs            # tail logs from all services
make ps              # container status
make rebuild         # rebuild images without cache

make venv            # create backend/.venv and install deps
make backend-test    # pytest in the host venv
make backend-fmt     # ruff format + autofix
make backend-lint    # ruff check (no fixes)

make migrate                          # alembic upgrade head (in container)
make makemigration m="message here"   # autogenerate a revision (in container)
```

## Frontend

```bash
cd frontend
npm install      # one-time
npm run dev      # next dev on :3000, hot reload
npm run build    # production build (used by the Dockerfile too)
```

Set `NEXT_PUBLIC_API_BASE=http://localhost/api` if you're running `next dev` against a Docker-hosted API.

## Adding dependencies

**Backend** — edit `backend/pyproject.toml`, then:
```bash
cd backend && VIRTUAL_ENV=.venv uv pip install -e ".[dev]"
make rebuild      # so the container picks them up too
```

**Frontend** — `cd frontend && npm install <pkg>`.

## Database migrations

Schema lives in `backend/app/models/`. To add or change a table:

1. Edit the SQLAlchemy model.
2. `make makemigration m="describe the change"` — Alembic autogenerates a revision under `backend/alembic/versions/`.
3. **Read the generated file.** Autogenerate is a starting point, not an answer — adjust it (especially for renames, data migrations, or pgvector indexes) before committing.
4. `make migrate` to apply.

## Local Python policy

Restated for emphasis (this is a hard rule):

- All Python work runs in **either** the Docker container **or** `backend/.venv`.
- Never `pip install` against system Python. Never `sudo pip`.
- `backend/.venv/` is git-ignored.

This keeps the host clean and contributors aligned.
