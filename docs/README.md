# Hiremesh docs

Living documentation. Built up alongside the code, milestone by milestone.

## Index

| Doc | Status | What it covers |
|---|---|---|
| [milestones.md](./milestones.md) | M0 | What's shipped per milestone (rear-view of `hiremesh-plan.md`) |
| [setup.md](./setup.md) | M0 | Prerequisites, first boot, env vars, bootstrapping the first admin |
| [dev-workflow.md](./dev-workflow.md) | M0 | venv vs Docker, common Make targets, running tests, Alembic |
| [architecture.md](./architecture.md) | M0 | Container topology, request flow, where things live in the repo |
| [auth.md](./auth.md) | M0 | How JWT/cookie auth works, role gating, admin-only user creation |
| [api.md](./api.md) | M0–M6 | API endpoint reference (kept in sync as endpoints are added) |
| [data-model.md](./data-model.md) | M1–M6 | Tables, relationships, audit trail invariants |
| [resumes-and-parsing.md](./resumes-and-parsing.md) | M2 | Storage, parser pipeline, LLM wrapper, sticky-edit invariant |
| [pipelines.md](./pipelines.md) | M3 | Candidate–job links, kanban, permanent stage-transition audit |
| [search-and-ask.md](./search-and-ask.md) | M4–M5 | Embeddings, semantic search, per-candidate + pool Q&A, SQL-safety boundary |
| [ops.md](./ops.md) | M6 | Backups (script + cron/systemd), deployment overview, health & metrics |
