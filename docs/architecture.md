# Architecture

What runs where, how requests flow, and where to find things in the repo.

## Container topology

```
                     ┌─────────────┐
                     │   Caddy     │   :80 (host)
                     │ reverse-prx │
                     └──┬───────┬──┘
                  /api  │       │  /
                        ▼       ▼
                  ┌─────────┐ ┌────────┐
                  │  API    │ │  Web   │
                  │ FastAPI │ │ Next.js│
                  └────┬────┘ └────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
  ┌────────┐     ┌──────────┐    ┌──────────┐
  │Postgres│     │  Redis   │    │ Worker   │
  │pgvector│     │ (broker) │    │ Celery   │
  └────────┘     └──────────┘    └──────────┘
```

Caddy is the only container with a host port binding (`:80`). Everything else talks over the internal compose network.

## Request flow

- **Browser → `/`**: Caddy → web (Next.js). Next.js's `proxy.ts` (formerly middleware) checks for the `hiremesh_session` cookie and redirects unauthenticated users to `/login`.
- **Browser → `/api/*`**: Caddy strips `/api` and forwards to the FastAPI container. Cookies travel automatically because the browser sees a single origin.
- **Server-side calls from Next.js → API**: an RSC layout (`app/(app)/layout.tsx`) forwards the inbound `cookie` header so server components can call `/auth/me` as the logged-in user.
- **Async work**: API enqueues jobs onto Redis; the worker container picks them up. (No tasks defined yet — the worker is a placeholder until M2.)

## Repo layout

```
hiremesh/
├── backend/                 # Python: FastAPI + workers
│   ├── app/
│   │   ├── api/             # HTTP route handlers
│   │   ├── core/            # config, db, security, deps, llm (later)
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # business logic, called from api/ and workers/
│   │   ├── workers/         # Celery app + tasks (M2+)
│   │   └── main.py          # FastAPI app + lifespan
│   ├── alembic/             # migrations
│   ├── tests/               # pytest suite
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .venv/               # host dev venv (git-ignored)
├── frontend/                # Next.js (App Router)
│   ├── app/
│   │   ├── (app)/           # authenticated routes share this layout
│   │   │   └── dashboard/
│   │   ├── login/
│   │   └── layout.tsx       # root
│   ├── components/
│   │   └── ui/              # shadcn-style primitives
│   ├── lib/
│   │   ├── api.ts           # typed fetch wrapper
│   │   └── utils.ts         # cn() helper
│   ├── proxy.ts             # cookie-gated route guard (Next 16 proxy)
│   ├── next.config.ts
│   └── Dockerfile
├── infra/
│   ├── docker-compose.yml   # the whole stack
│   ├── Caddyfile            # reverse-proxy config
│   ├── .env.example
│   └── .env                 # git-ignored, your local secrets
├── docs/                    # this folder
├── Makefile
├── hiremesh-plan.md         # product + milestones
├── README.md
└── LICENSE                  # MIT
```

## Why these choices

- **One DB image (pgvector)** — relational + vector data live in the same Postgres. Cheaper to operate than a split.
- **Celery, not RQ/Arq** — most resume-parsing pipelines benefit from retries, beat schedules, and structured task chaining. We bring this in starting M2.
- **Caddy, not nginx** — automatic TLS in prod, and the dev config stays a 10-line `Caddyfile`.
- **Next.js App Router** — server components let us forward auth cookies cleanly and ship streaming search results later in M4–M5.
- **`proxy.ts` (Next 16)** — replaces the deprecated `middleware.ts`. Same idea, different file name and export.

## Where the AI layer fits in (preview)

LLM calls go through a thin `app/core/llm.py` wrapper around LiteLLM. Each task (parsing, embeddings, per-candidate Q&A, pool-Q&A classifier, SQL gen, answer synthesis) is a separate role with its own env var, so models can be swapped per task without code changes. M2 introduces the first role (resume parsing).
