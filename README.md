# Hiremesh

Open-source, AI-powered talent base for recruitment agencies. Search your own pool first, in plain English, before sourcing externally.

> **Status:** in active development. See [`hiremesh-plan.md`](./hiremesh-plan.md) for the full plan and milestones.

## What it does

- Single talent pool across all clients/jobs
- Resume parsing (PDF/DOCX) into structured candidate fields
- Per-job pipelines with customizable Kanban stages
- Permanent stage-history audit trail
- Plain-English search across the pool ("backend engineer with fintech experience in Pune")
- Per-candidate Q&A with citations from resume + notes
- Pool Q&A that routes between SQL aggregation and semantic retrieval

## Quickstart

```bash
git clone <this repo>
cd hiremesh
cp infra/.env.example infra/.env   # then edit secrets
make up                            # boots full stack on http://localhost
```

Full setup, dev workflow, and architecture docs live in [`docs/`](./docs/).

## Built with

Hiremesh stands on a lot of excellent open-source work. Huge thanks to the maintainers of every project below.

### Backend (Python)

- **[FastAPI](https://fastapi.tiangolo.com/)** — the API framework. Type-driven routing + auto-generated OpenAPI docs do most of our request validation for free.
- **[Uvicorn](https://www.uvicorn.org/)** — the ASGI server FastAPI runs on.
- **[SQLAlchemy](https://www.sqlalchemy.org/)** — ORM. The 2.0 typed-mapped style is used throughout `app/models/`.
- **[Alembic](https://alembic.sqlalchemy.org/)** — schema migrations.
- **[Pydantic](https://docs.pydantic.dev/)** & **[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)** — request/response schemas and env-driven config. The pool-Q&A SQL safety boundary is built on Pydantic `Literal` types.
- **[psycopg](https://www.psycopg.org/)** — Postgres driver (v3, async-capable).
- **[Passlib](https://passlib.readthedocs.io/)** + **[argon2-cffi](https://argon2-cffi.readthedocs.io/)** — password hashing.
- **[PyJWT](https://pyjwt.readthedocs.io/)** — session tokens in the auth cookie.
- **[Celery](https://docs.celeryq.dev/)** + **[redis-py](https://github.com/redis/redis-py)** — the worker queue for resume parsing and embedding tasks.
- **[boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)** — S3 client (works against MinIO in dev, R2 / S3 in prod).
- **[LiteLLM](https://github.com/BerriAI/litellm)** — multi-provider LLM router. This is the keystone that lets you swap between OpenAI / Anthropic / OpenRouter / Voyage / Cohere / Ollama with one env var. Massive thanks to the [BerriAI](https://github.com/BerriAI) team.
- **[pgvector](https://github.com/pgvector/pgvector)** + **[pgvector-python](https://github.com/pgvector/pgvector-python)** — the vector column type and ANN index that power semantic search across the talent pool. Thanks to [Andrew Kane](https://github.com/ankane).
- **[pypdf](https://github.com/py-pdf/pypdf)** + **[python-docx](https://python-docx.readthedocs.io/)** — resume text extraction.
- **[python-multipart](https://github.com/Kludex/python-multipart)** — file upload parsing.
- **Dev tooling**: **[pytest](https://docs.pytest.org/)**, **[httpx](https://www.python-httpx.org/)**, **[ruff](https://github.com/astral-sh/ruff)**, **[mypy](https://mypy-lang.org/)**, **[uv](https://github.com/astral-sh/uv)** (venv + installer). The folks at [Astral](https://astral.sh/) have made Python dev dramatically nicer.

### Frontend (TypeScript / React)

- **[Next.js](https://nextjs.org/)** — the App Router, server components, route handlers, and middleware.
- **[React](https://react.dev/)** — UI runtime.
- **[Tailwind CSS](https://tailwindcss.com/)** (v4) — styling. With **[@tailwindcss/postcss](https://tailwindcss.com/docs/installation/using-postcss)**, **[tailwind-merge](https://github.com/dcastil/tailwind-merge)**, and **[tw-animate-css](https://github.com/midudev/tw-animate-css)**.
- **[shadcn-style components](https://ui.shadcn.com/)** — our `components/ui/` (Button, Card, Input, Label, Textarea) follows the shadcn pattern (copy-paste primitives built on Radix conventions). Thanks to [shadcn](https://github.com/shadcn-ui/ui).
- **[class-variance-authority](https://cva.style/)** + **[clsx](https://github.com/lukeed/clsx)** — variant + class-name utilities used in those components.
- **[@dnd-kit/core](https://docs.dndkit.com/)** — the drag-and-drop kanban on the job board.
- **[TypeScript](https://www.typescriptlang.org/)** + **[ESLint](https://eslint.org/)** — type safety and linting.

### Infrastructure

- **[PostgreSQL](https://www.postgresql.org/)** — the database, via the official **[pgvector/pgvector](https://hub.docker.com/r/pgvector/pgvector)** image which bundles the vector extension.
- **[Redis](https://redis.io/)** — Celery broker.
- **[MinIO](https://min.io/)** — S3-compatible object storage for resume blobs in dev.
- **[Caddy](https://caddyserver.com/)** — reverse proxy with automatic HTTPS in prod.
- **[Docker](https://www.docker.com/)** & Compose — orchestration.

### Model providers

Hiremesh routes to whichever LLM/embedding provider you configure. The default examples in our docs use [OpenAI](https://openai.com/) and [OpenRouter](https://openrouter.ai/), but the code path supports [Anthropic](https://www.anthropic.com/), [Voyage](https://www.voyageai.com/), [Cohere](https://cohere.com/), [Ollama](https://ollama.com/), and anything else LiteLLM supports.

If we missed crediting something you maintain, please open an issue — we want every shoulder we're standing on to be visible.

## License

MIT — see [`LICENSE`](./LICENSE).
