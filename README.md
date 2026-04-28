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

## License

MIT — see [`LICENSE`](./LICENSE).
