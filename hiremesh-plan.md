# Hiremesh — Open-Source AI-Powered Talent Base

A talent-pool-first recruitment system for an agency serving multiple clients. The core idea: recruiters should search their own pool before sourcing externally.

---

## 1. Product Scope (v1)

### Core entities
- **Clients** — companies the agency recruits for.
- **Jobs** — open positions under a client (JD, location, experience range, CTC range, status: open / on-hold / closed).
- **Candidates** — the talent pool. One profile per person.
- **Resumes** — PDF/DOCX, parsed into structured fields. Multiple versions per candidate; one marked primary.
- **Notes** — recruiter-authored, attached to a candidate (global) OR to a candidate–job link.
- **Stages** — customizable pipeline steps. System-wide template (admin-editable) + per-job stages deep-copied from the template when a job is created.
  - Default stages: `Sourced/Teaser` → `InMail to be sent` → `Email cadence initiated` → `InMail sent` → `Follow-Up` → `Not Interested` → `Interested` → `Submitted`.

### Users
- **Admin** — manages users, edits the system-wide stage template.
- **Recruiter** — everything else.
- All users see all data (no row-level access in v1).

### Key behaviors
- Manual edits to candidate fields are **sticky** — re-parsing a resume never overwrites human edits.
- Stage history is preserved permanently (audit trail), even if a candidate is unlinked from a job.
- Soft-delete on candidates.
- All AI work (parsing, embedding, search) runs async — UI never blocks on it.

---

## 2. Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| Database | PostgreSQL + pgvector |
| Validation / structured output | Pydantic |
| Queue / async | Redis + Celery |
| Object storage | Cloudflare R2 |
| Frontend | Next.js (App Router) + React + Tailwind + shadcn/ui + @dnd-kit |
| AI / LLM gateway | LiteLLM |
| Auth | Self-hosted JWT in HTTP-only cookies (PyJWT + passlib[argon2]) |
| Infra | Single VPS, Docker Compose |

### Containers
- `postgres` — pgvector image (relational + vector data, single DB).
- `redis` — Celery broker + cache.
- `api` — FastAPI app.
- `worker` — Celery worker(s).
- `web` — Next.js (served behind Caddy).
- `caddy` — TLS + reverse proxy.

### Volumes
- `postgres_data` — persistent DB.

### Local Python policy (no system-Python touching)
- All Python work — installs, tests, linting, Alembic, ad-hoc scripts — runs inside an **isolated venv**, never against the host's system Python.
- Two acceptable execution paths; pick per task:
  1. **Inside the `api` / `worker` Docker container** (preferred for anything DB/Redis/R2-touching) — `docker compose exec api ...`. The container already has its own interpreter and deps; nothing leaks to the host.
  2. **Host venv** at `backend/.venv` for editor tooling and quick offline work (type-checking, formatters, unit tests with no external deps). Created via `python -m venv backend/.venv` and activated explicitly per shell.
- **Never** `pip install` against system Python. **Never** use `sudo pip`. The host's `python3` is treated as read-only.
- `backend/.venv/` is git-ignored.
- Dependencies are pinned in `backend/pyproject.toml` (managed with `uv` or `pip-tools`); the same lock file is used by both the Dockerfile and the host venv so they stay in sync.
- A `Makefile` (or `justfile`) exposes the common entry points (`make sh`, `make test`, `make migrate`, `make worker`) so contributors don't have to remember whether something runs in-container or in-venv.

---

## 3. Data Model (high level)

Tables:
- `users` (id, email, password_hash, role, name, created_at)
- `clients` (id, name, notes, created_at)
- `jobs` (id, client_id, title, jd_text, location, exp_min, exp_max, ctc_min, ctc_max, status, created_at, created_by)
- `candidates` (id, full_name, email, phone, location, current_company, current_title, total_exp_years, current_ctc, expected_ctc, notice_period_days, skills[], summary, deleted_at, created_at)
- `candidate_field_overrides` (candidate_id, field_name, value, set_by, set_at) — drives "sticky" edits
- `resumes` (id, candidate_id, r2_key, mime, is_primary, parsed_json, parse_status, created_at)
- `candidate_embeddings` (candidate_id, source: resume|notes|profile, content, vector, updated_at)
- `notes` (id, candidate_id, job_link_id NULL, author_id, body, created_at)
- `stage_templates` (id, name, position) — system-wide template, admin-editable
- `job_stages` (id, job_id, name, position) — deep-copied per job
- `candidate_jobs` (id, candidate_id, job_id, current_stage_id, linked_at)
- `stage_transitions` (id, candidate_job_id, from_stage_id, to_stage_id, by_user, at) — permanent audit
- `audit_log` (id, actor, action, entity, entity_id, payload, at) — generic write log

Indexes: trigram on candidate names/skills, ivfflat on `candidate_embeddings.vector`, btree on FK + status fields.

---

## 4. Backend Architecture

### Module layout (FastAPI)
```
app/
  api/
    auth.py        # login, logout, me
    clients.py
    jobs.py
    candidates.py
    resumes.py     # upload, list, set primary
    notes.py
    stages.py      # template + per-job
    pipeline.py    # kanban moves, transitions
    search.py      # semantic + filtered talent search
    ask.py         # per-candidate + cross-pool Q&A
    admin.py
  core/
    config.py
    db.py
    security.py    # password hashing, JWT, cookie helpers
    deps.py        # auth/role dependencies
    storage.py     # R2 client wrapper
    llm.py         # LiteLLM wrapper, prompt templates
  models/          # SQLAlchemy
  schemas/         # Pydantic
  services/
    candidates.py  # apply overrides, merge parsed + manual
    resumes.py     # upload + enqueue parse
    pipeline.py    # stage move + transition logging
    search.py      # query routing (SQL vs semantic vs hybrid)
    parsing.py     # parse → structured Pydantic → DB
    embeddings.py
  workers/
    celery_app.py
    tasks/
      parse_resume.py
      embed_candidate.py
      reindex.py
  main.py
```

### Async pipelines
1. **Resume upload** → store in R2 → insert `resumes` row → enqueue `parse_resume` → worker fills `parsed_json`, applies fields to `candidates` (skipping any field present in `candidate_field_overrides`) → enqueue `embed_candidate`.
2. **Candidate edit** → write to `candidates` AND `candidate_field_overrides` for each changed field → enqueue `embed_candidate`.
3. **Notes added** → enqueue `embed_candidate` (re-embed notes source).

### Search routing (Ask + Search)
- **Per-candidate Q&A** — RAG over that candidate's resume + notes; return answer + citations.
- **Pool Q&A** — classifier (small LLM call via LiteLLM) decides:
  - **Aggregation/filter** ("how many Python devs in Pune in `Interested`") → translate to SQL via constrained Pydantic schema → execute → summarize.
  - **Semantic** ("backend engineer with fintech experience") → vector search over `candidate_embeddings` + optional structured filters → rerank → return ranked candidates.
  - **Hybrid** — both, then merge.
- All filters (location, skills, experience, current stage) layer on top of either path.

---

## 5. Frontend Architecture (Next.js App Router)

```
app/
  (auth)/login/
  (app)/
    dashboard/
    clients/[id]/
    jobs/[id]/                # detail + kanban
    candidates/
      page.tsx                # search + list
      [id]/page.tsx           # profile, resumes, notes, ask-this-candidate
    pool/ask/                 # cross-pool Q&A
    admin/
      users/
      stages/                 # edit system template
  api/                        # thin BFF if needed (otherwise call FastAPI directly)
components/
  kanban/                     # @dnd-kit board
  candidate/                  # profile blocks, edit forms (sticky-aware)
  resume/                     # upload, viewer, version switcher
  search/                     # query bar + filter chips
  ask/                        # chat-style Q&A with citations
  ui/                         # shadcn primitives
lib/
  api.ts                      # typed fetch wrapper
  auth.ts                     # cookie/session helpers (middleware)
middleware.ts                 # gate (app) routes on session cookie
```

### Notable interactions
- **Kanban** — drag a card → optimistic update → POST stage transition → toast on failure with revert.
- **Candidate edit** — fields edited inline; UI shows a small "manually set" indicator on overridden fields (so it's clear re-parse won't overwrite).
- **Search** — single input with optional filter chips; results stream in (semantic search can be slow).
- **Ask** — chat-style with citations linking to resume page / note.

---

## 6. Auth

- Email + password (argon2 hash).
- Login issues a signed JWT (short-lived, e.g. 24h) in an HTTP-only, Secure, SameSite=Lax cookie.
- Next.js middleware reads cookie → forwards to API → API verifies signature + expiry.
- Roles: `admin`, `recruiter`. Admin-only endpoints guarded by FastAPI dependency.
- No refresh tokens in v1; re-login on expiry.

### Signup / user creation
- **No public signup.** All accounts are created by an admin from the admin UI.
- **First admin** is bootstrapped at deploy time:
  - On first boot, if zero users exist, the API reads `BOOTSTRAP_ADMIN_EMAIL` + `BOOTSTRAP_ADMIN_PASSWORD` from env and creates the initial admin.
  - After that, the bootstrap path is a no-op even if the env vars stay set.
- Admin creates users with `{email, name, role}` + a temporary password (or an email-able invite link in a later milestone). New user must change password on first login.

---

## 7. Storage & Files

- Resumes stored in R2 under `resumes/{candidate_id}/{resume_id}.{ext}`.
- API generates **pre-signed download URLs** for the frontend (short TTL).
- Upload: client → API (multipart) → API streams to R2 → enqueue parse.
- Parsed JSON stored in `resumes.parsed_json` (jsonb) — keeps the full parser output for debugging/replay.

---

## 8. AI / LLM Layer

All LLM calls go through a thin `core/llm.py` wrapper around LiteLLM so models are swappable per task. Resume **parsing** and **embeddings** are intentionally separate models. Defaults are cheap and can be upgraded per task without code changes (env vars per role).

| Task | Default (cheap) | Notes |
|---|---|---|
| Resume parsing | `gpt-4o-mini` (or `claude-haiku-4-5`) | Pydantic-constrained structured output |
| Embeddings | `text-embedding-3-small` | 1536-dim; cheap, good baseline |
| Per-candidate Q&A | `gpt-4o-mini` | RAG over one candidate |
| Pool Q&A classifier | `gpt-4o-mini` | Picks SQL / semantic / hybrid |
| Pool Q&A SQL gen | `gpt-4o-mini` | Constrained to a read-only view |
| Pool Q&A answer synthesis | `gpt-4o-mini` | Summarizes results + citations |

Roles are wired as env vars (`LLM_PARSE_MODEL`, `LLM_EMBED_MODEL`, `LLM_QA_MODEL`, …) so any one task can be swapped to a stronger model later without touching code.

Prompts live in `app/core/prompts/` as plain `.md` files, loaded at startup.

---

## 9. Build Plan (sequenced milestones)

### M0 — Skeleton (1 week)
- Repo + Docker Compose (postgres, redis, api, worker, web, caddy).
- FastAPI hello + Next.js hello, both behind Caddy.
- Alembic baseline migration.
- Auth: bootstrap-admin-from-env, login, logout, `/me`, admin-only `POST /users`. No public signup.

### M1 — Core CRUD (1–2 weeks)
- Clients, Jobs, Candidates (manual create/edit) — full CRUD UIs.
- System stage template + per-job copy on creation.
- Notes (candidate-scoped only at first).
- Soft-delete candidates.

### M2 — Resumes + Parsing (1–2 weeks)
- R2 wired up; resume upload + list + set-primary.
- Celery worker; `parse_resume` task with Pydantic schema.
- Sticky-edit logic via `candidate_field_overrides`.
- Resume viewer in candidate profile.

### M3 — Pipeline / Kanban (1 week)
- `candidate_jobs` link, `stage_transitions` log.
- Per-job Kanban with @dnd-kit, optimistic moves, transition history view.
- Job-link-scoped notes.

### M4 — Search & Embeddings (1–2 weeks)
- `embed_candidate` task; pgvector ivfflat index.
- Talent search: semantic + filter chips (location, skills, experience, stage).
- Reindex job for backfills.

### M5 — Ask (1–2 weeks)
- Per-candidate Q&A with citations.
- Pool Q&A with classifier → SQL/semantic/hybrid routing.
- Streaming responses on the frontend.

### M6 — Admin & polish (1 week)
- Admin: user management, stage template editor.
- Audit log viewer.
- Backups (nightly `pg_dump` to R2).
- Basic metrics (queue depth, parse success rate).

---

## 10. Open Questions / Decisions Deferred

- **Resume parser model** — defaulting to `gpt-4o-mini` for now; revisit during M2 on real resumes.
- **Embedding model** — defaulting to `text-embedding-3-small`; can swap to local (bge) later if cost or data-locality demands it.
- **SQL-gen safety** — restrict to a curated read-only view of `candidates` + joined fields, not raw schema (decision made; implement in M5).
- **Multi-tenant?** — out of scope for v1 (single agency, all-users-see-all).
- **Email/InMail integrations** — out of scope; stages reflect external activity but the app doesn't send.
- **Rate-limit / quota for AI calls** — add basic per-user daily cap before exposing Ask broadly.

---

## 11. Repo Layout

```
hiremesh/
  backend/
    app/
    alembic/
    pyproject.toml
    uv.lock                 # or requirements.lock
    .venv/                  # git-ignored; host-side dev venv
    Dockerfile
    Makefile                # make sh / test / migrate / worker
  frontend/
    app/
    components/
    lib/
    package.json
    Dockerfile
  infra/
    docker-compose.yml
    Caddyfile
    .env.example
  docs/
    hiremesh-plan.md   # this file (move here once stable)
    api.md
    schema.md
```
