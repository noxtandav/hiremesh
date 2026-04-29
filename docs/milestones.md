# Milestone log

What's actually shipped and verified, milestone by milestone. The forward-looking plan lives in [`hiremesh-plan.md`](../hiremesh-plan.md); this is the rear-view.

## M0 — Skeleton + auth ✅

**Scope:** repo skeleton, Docker Compose with the full container topology, FastAPI hello + Next.js hello behind Caddy, Alembic baseline, admin-bootstrapped auth (login, logout, /me, change password, admin POST /users).

**Shipped:**
- `backend/` — FastAPI app, Alembic baseline migration (`users` table), uv-managed deps, host venv.
- `frontend/` — Next.js 16 (App Router) + Tailwind v4 + shadcn-style primitives + `proxy.ts` cookie gate.
- `infra/` — `docker-compose.yml` with postgres(pgvector) / redis / api / worker / web / caddy, plus a Caddyfile that fronts both.
- `Makefile` — `up`, `down`, `migrate`, `backend-test`, `venv`, etc.
- `docs/` — setup, dev workflow, architecture, auth, api reference.

**Verified:**
- 13 backend pytest cases pass against an in-memory sqlite (bootstrap idempotency, login good/bad, /me, role gating, change password, duplicate email).
- All three Docker images (`api`, `worker`, `web`) build cleanly.
- `npx next build` produces all 4 routes (`/`, `/dashboard`, `/login`, `/_not-found`) and a `Proxy (Middleware)` entry, types green.
- **Full stack end-to-end through Caddy on host port 80:**
  - `GET http://localhost/api/health` → `{"status":"ok"}` (200)
  - `GET http://localhost/login` → `200` (Next.js login page)
  - `POST http://localhost/api/auth/login` → `200`, sets the `hiremesh_session` cookie, returns the bootstrap admin
  - `GET http://localhost/api/auth/me` with the cookie → `200` with the same user
  - This proves: Alembic migrated against the real Postgres, the `users` table was created, the bootstrap admin was seeded from env vars, the Caddy reverse proxy strips `/api` and forwards correctly, the frontend serves at `/`, and the cookie travels round-trip.

## M1 — Core CRUD ✅

**Scope:** clients, jobs (with per-job stage copy), candidates (with soft-delete), candidate-scoped notes, admin-editable stage template.

**Shipped:**
- Models: `clients`, `jobs`, `job_stages`, `candidates`, `notes`, `stage_templates`. Migration `a9b9b6f3d3ac`.
- Default 8-stage template seeded once at first boot (idempotent).
- API endpoints (full CRUD for each entity, plus `POST /candidates/{id}/restore`).
- Frontend: `/clients`, `/clients/[id]`, `/jobs/[id]`, `/candidates`, `/candidates/[id]`, `/admin/stages` — list/detail/create flows. Admin-only nav link to stages, route-guarded server-side.
- Range validators (exp_min ≤ exp_max, ctc_min ≤ ctc_max).
- Note edit/delete restricted to author or admin.

**Verified:**
- 38 backend tests pass (auth + stages + clients/jobs + candidates + notes).
- Frontend `next build` produces all 9 routes, types green.
- **End-to-end smoke through Caddy on host port 80:**
  - Login → seed stage template visible (8 default stages)
  - Create client → create job → response includes `stages: [...]` length 8 ✓ (deep-copy invariant proven against real Postgres)
  - Create candidate → add note → soft-delete candidate → list with `include_deleted=false` returns 0, `include_deleted=true` returns 1
- Stage-template edits do **not** retroactively affect existing jobs (test + manual verification).

**Known limits in M1 (deferred deliberately):**
- No full-text or vector search yet — `GET /candidates` is a plain offset/limit list. Search is M4.
- No bulk operations, no CSV import.
- The job page renders stages read-only — kanban arrives in M3 alongside `candidate_jobs` and `stage_transitions`.

## M2 — Resumes + Parsing ✅

**Scope:** S3-compatible storage, async resume parsing through Celery + LiteLLM, the sticky-edit invariant.

**Shipped:**
- New tables: `resumes`, `candidate_field_overrides`. Migration `3ff08e5c873b`.
- Storage: MinIO container in dev compose (S3-compatible), R2 in prod via the same boto3 client. Pre-signed download URLs with a 5-minute TTL.
- Celery worker booting against Redis with `parse_resume` task registered.
- LiteLLM-backed `app/core/llm.py` with role-based env vars (`LLM_PARSE_MODEL`, `LLM_API_KEY`). `LLM_PARSE_MODEL=fake` (the default) gives deterministic dummy output without an API key — dev and tests both use it.
- Resume API: upload (`POST /candidates/{id}/resumes`), list, set-primary, re-parse, delete, presigned-URL.
- **Sticky-edit invariant**: `PATCH /candidates/{id}` records every changed field in `candidate_field_overrides`; `apply_parsed_fields` skips overridden fields. Both code paths live in `app/services/candidates.py` so the rule cannot be bypassed.
- Frontend: upload widget on the candidate page with parse-status badges, primary toggle, re-parse, delete, and download via presigned URL. Polls every 1.5s while anything is parsing.

**Verified:**
- 51 backend tests pass (38 from M0–M1 + 13 new for M2: 5 sticky-override + 8 resume pipeline).
- Frontend `next build` clean — all routes generate, types green.
- **End-to-end against the live stack** (Caddy → api → Celery worker → MinIO):
  - Upload a (text-as-)PDF → status moves `pending → done` → candidate's `full_name`, `email`, `skills`, `summary` filled in by the fake parser.
  - Manually `PATCH location=Bangalore`. Upload a second resume containing "Location: Pune". Result: `full_name` and `skills` updated from the new resume; **`location` stayed Bangalore**. Sticky-edit invariant proven on the live system.
- pre-signed download URLs work end-to-end (browser-reachable via `S3_PUBLIC_ENDPOINT`).

**Known limits in M2 (deferred deliberately):**
- No OCR — resumes that are scanned-image PDFs only extract whatever pypdf can recover. Most modern resumes have a text layer; if not, the LLM still gets a noisy fallback decode. We can add Tesseract later if needed.
- Default `LLM_PARSE_MODEL` is `fake`. To use a real model in dev, set `LLM_PARSE_MODEL=gpt-4o-mini` (or any LiteLLM id) and `LLM_API_KEY` in `infra/.env`.
- No re-parse-on-edit triggering (parsing is only invoked on upload or explicit re-parse).
- No file-type detection beyond the supplied content-type header.

## M3 — Pipeline / Kanban ✅

**Scope:** candidate↔job links, permanent stage-transition audit, kanban with drag-and-drop, link-scoped notes.

**Shipped:**
- New tables: `candidate_jobs`, `stage_transitions`. `notes.candidate_job_id` added (nullable). Migration `75afa9bfaebf`.
- API: `GET /jobs/{id}/board`, `POST /jobs/{id}/candidates`, `PATCH/DELETE /candidate-jobs/{id}`, `GET /candidate-jobs/{id}/transitions`, `GET/POST /candidate-jobs/{id}/notes`.
- All state changes go through `app/services/pipeline.py`, which writes the audit row in the same transaction as the candidate-jobs change. The two cannot drift.
- Frontend: drag-and-drop kanban on the job page (`@dnd-kit/core`), with optimistic updates, rollback on failure, a candidate picker, and a per-link drawer that shows transition history and link-scoped notes.

**Verified:**
- 62 backend tests pass (51 from M0–M2 + 11 new for M3).
- Frontend `next build` clean — all routes generate.
- **Permanent-audit invariant proven on the live system:**
  1. Linked a candidate → board shows them at stage 0; `stage_transitions` has 1 row (`from=NULL → to=stage_0`).
  2. Moved them two stages forward → `stage_transitions` has 2 rows.
  3. **Unlinked**. Board shows 0 candidates. `candidate_jobs` row gone. `stage_transitions` table still has all 3 rows including the auto-written final `to_stage_id=NULL` "left the pipeline" marker — confirmed via direct `psql` query against the live Postgres.

**Known limits in M3 (deferred deliberately):**
- The candidate picker filters the whole pool client-side. Real semantic search arrives in M4 and will replace this.
- The drag-and-drop has no within-column ordering — the order inside a column is just `linked_at` ascending. Adding intra-column ordering would mean a `position` column on `candidate_jobs`; not worth it until users ask.
- Per-job stage editing is still admin-template-only. If a job's stages need to differ from the template after creation, you currently can't edit them in the UI (only via direct DB / future API).

## M4 — Search & Embeddings ✅

**Scope:** pgvector storage, async embedding worker, plain-English semantic search with filter chips, admin reindex, search-driven candidate UI.

**Shipped:**
- `candidate_embeddings` (pgvector + ivfflat index). Migration `aa01c8e2f4d6` (handwritten — autogenerate doesn't infer `CREATE EXTENSION`). Falls back to JSON on SQLite for tests via a `VectorColumn` TypeDecorator.
- `app/core/embeddings.py` — LiteLLM wrapper with role-based env var (`LLM_EMBED_MODEL`). Default `fake` mode produces deterministic 1536-dim BoW-like vectors that actually cluster by token overlap; real models swap in via env var.
- `embed_candidate` Celery task. Auto-fires when a `parse_resume` task completes; admin can also fire it for everyone.
- `POST /search/candidates` — filter-only or semantic+filter. Filters: location, skills (AND), exp range, current `stage_name` on any job. Soft-deleted candidates excluded.
- `POST /admin/reindex/candidates` (admin only) — enqueues an embed task per active candidate.
- Frontend: search-driven `/candidates` with debounced live search, chip-based filters (skills/location/exp/stage), score badges, admin "Reindex pool" action.

**Verified:**
- 75 backend tests pass (62 from M0–M3 + 13 new for M4: 6 embedder + 7 search). Tests cover: smart-fake clusters by token overlap (semantic ranks Asha first vs unrelated profiles), filter intersection, stage-name filter via subquery, soft-delete exclusion.
- Frontend `next build` clean — all routes generate.
- **Live system, real Postgres + pgvector + Celery worker:**
  - `POST /admin/reindex/candidates` → `{enqueued: 2}` → embeddings populated within 5 seconds.
  - Query "application support ITIL technical lead PMP" → AMIT (whose resume contains those tokens) ranks at **score=0.557** vs unrelated candidate at **0.013** — clear ~40× separation.
  - Query "engineer" + `location=Bangalore` → returns exactly the one Bangalore candidate. Filter intersects with semantic ranking as designed.

**Known limits in M4 (deferred deliberately):**
- One combined document per candidate (`source='combined'`). The plan mentions per-source rows for finer retrieval; can split when relevance demands it.
- No live re-embed on PATCH /candidates or note-add. Admin reindex covers periodic refresh; live re-embed is a one-line addition when freshness drift becomes a real problem.
- ivfflat with `lists=100` — fine for thousands of candidates. Tune up (or switch to HNSW) if the pool grows.
- The fake embedder is BoW-style — token overlap drives cosine. No synonym handling, no real semantic understanding. Switch to `text-embedding-3-small` (one env var) for production search quality.

## M5 — Ask ✅

**Scope:** per-candidate Q&A with citations; pool Q&A that routes between SQL aggregation, semantic retrieval, and hybrid; safe SQL via Pydantic-constrained queries against a curated read-only view.

**Shipped:**
- New view `v_candidate_search` (migration `bb02d6f3a8e1`) — flat read-only join of candidates + their current pipeline placement + counts. The only surface the pool-Q&A SQL path can read.
- `app/services/qa_candidate.py` — per-candidate RAG: builds a context block from profile + primary resume + all notes, asks the model, returns answer + citations indexed by source.
- `app/services/qa_pool.py` — classifier picks `structured | semantic | hybrid`; SQL gen emits a Pydantic `StructuredQuery`; synthesizer composes the answer.
- `app/services/qa_pool_query.py` — the safety boundary. `ALLOWED_COLUMNS` whitelist + `FilterClause` Literal-typed columns/ops. The translator builds parameterized SQL; **the LLM cannot emit SQL**.
- Endpoints: `POST /ask/candidate/{id}` and `POST /ask/pool`.
- `LLM_QA_MODEL` env var (default `fake`) covers all three Q&A roles.
- Frontend: per-candidate ask panel on the candidate detail page; new `/ask` page for pool questions with route-tag, sample chips, rows table, and citation list linking back to candidate pages.

**Verified:**
- 101 backend tests pass (75 from M0–M4 + 26 new for M5):
  - 5 per-candidate Q&A tests (citations include profile/resume/note correctly; soft-deleted 404).
  - 13 SQL-safety tests (every Pydantic guard fires; query compiler produces correct SQL with bound params for all op types).
  - 8 pool dispatch tests (classifier picks correctly; semantic ranks the right candidate).
- Frontend `next build` clean.
- **End-to-end against the live stack** (real OpenRouter `text-embedding-3-small` for embeddings, `fake` for parsing/QA):
  - **Per-candidate Q&A** on AMIT MALVI: returned profile + resume citations and quoted his 14 years of Application Support / ITIL experience verbatim.
  - **Structured route** "How many candidates are there?" → 2. "How many python developers are there?" → 1 (correctly filtered by `contains_skill`).
  - **Semantic route** "backend engineer with technical lead experience" → AMIT (Technical Lead) ranks first.
  - **Hybrid route** "how many python developers have ITIL experience" → classifier picked `hybrid`, structured filter narrowed to 1, semantic ranking confirmed.
- **`v_candidate_search` exercised live**: SQL gen emitted `WHERE LOWER(CAST(skills AS TEXT)) LIKE :p0` against the view, executed cleanly.

**Known limits in M5 (deferred deliberately):**
- No streaming — punted as polish. Whole answers come back in one response.
- One `LLM_QA_MODEL` covers classifier + SQL gen + synthesis. Split per role only if quality demands.
- No multi-turn / conversation history.
- No Q&A audit log (M6).
- No result caching.
- Fake-mode SQL gen catches simple patterns (skills/location/exp/count). For multi-clause group-by questions a real `LLM_QA_MODEL` produces better-shaped queries.

## M6 — Admin & polish ✅

**Scope:** audit log + viewer, full user management surface, metrics endpoint, admin frontend, backup script + ops doc.

**Shipped:**
- New `audit_log` table (migration `cc03e9a4b2f7`). Best-effort `record()` helper using a SAVEPOINT so audit failures can never poison the caller's transaction.
- Audit calls wired into login/logout, user create/update/reset-password, client create/delete, job create/delete, candidate create/soft-delete/restore, reindex/embeddings.reset.
- User management API: `GET /users`, `PATCH /users/{id}` (role/active/name with self-protection: can't deactivate yourself, can't demote the last admin), `POST /users/{id}/reset-password`.
- `GET /admin/audit-log` with entity + action filters and `actor_name` hydration.
- `GET /admin/metrics` returning candidate/job/client/resume/user counts, embedding coverage %, Celery queue depth, configured model ids.
- Admin frontend: nested layout under `/admin` with sub-nav (Users / Stages / Audit log / Metrics). Users page supports inline role change, deactivate/reactivate, password reset modal, and creation. Audit log has live-filterable entity/action search. Metrics page renders the JSON as stat cards with reindex / reset-embeddings actions.
- `infra/backups/pg_dump_to_s3.sh` — runnable backup script that uploads gzipped `pg_dump --format=custom` output to any S3-compatible bucket and prunes by retention. Documented in `docs/ops.md` along with restoration steps and three scheduling options.

**Verified:**
- 114 backend tests pass (101 + 13 new for M6: 6 user-mgmt + 7 audit/metrics).
- Frontend `next build` clean — 14 routes including the four admin pages.
- **End-to-end on the live stack:**
  - Login → audit row written (`login` / `user#1`).
  - Create a client → audit row written (`client.create` / `client#3` with `{name}` payload).
  - `GET /admin/audit-log` returned both rows with hydrated `actor_name=Admin`.
  - `GET /admin/metrics` returned the actual production state: 2 active candidates, 100% embedding coverage, 3 done resumes, OpenRouter models, Celery queue 0.
- User-management self-protection rules verified: can't deactivate yourself (400), can't demote the last admin to recruiter (400), but can deactivate a recruiter and they can no longer log in (401).

**Known limits in M6 (deferred deliberately):**
- Audit doesn't capture every PATCH — note edits and per-field candidate edits aren't logged here. Per-field candidate provenance lives in `candidate_field_overrides` (M2). If you need a more granular log, switching to SQLAlchemy mapper events on a per-table basis is the right next step.
- Metrics endpoint is JSON, not Prometheus exposition format. Adding `/metrics` for Prometheus is straightforward when there's a scraper.
- Backups are a script, not a container. We document three scheduling options (cron / systemd timer / GitHub Actions) but don't bundle one — backup schedules and credentials want to be deploy-specific.
- Object-storage backups (resume blobs) are NOT included — point R2 versioning + replication at the bucket instead.
- No live-streaming metrics (page-load only). Polling can be added when there's a real reason to watch.

## All milestones complete 🎉

Hiremesh's planned scope (M0–M6) is shipped. See [`hiremesh-plan.md`](../hiremesh-plan.md) for the original plan; this file is the rear-view of what was actually built and verified at each step.

## Post-M6 enhancements

Iterations after the original plan, driven by real-world use:

**Bulk import + resume-only intake (extends M2):**
- `POST /candidates/bulk-import` — upload many PDFs/DOCXs at once, one candidate per file with a filename-derived placeholder name; per-file errors reported in the response without aborting the batch.
- The frontend "New candidate" button is now a single-file resume drop zone that calls bulk-import internally. Manual-form entry is still possible via API but no longer exposed in the UI.
- "Bulk import" button alongside it on the candidates list page.

**Same-origin resume serving + in-page preview (extends M2):**
- `GET /resumes/{id}/file` streams resume bytes through the API instead of a presigned S3 URL — fixes preview/download when the user's browser is on a different host than MinIO/R2 (LAN access, Caddy front-door, etc.).
- `ResumePreview` component renders the primary resume inline via an iframe at `/api/resumes/{id}/file#view=FitH`. DOCX/DOC fall back to a download link.

**Full resume body in Q&A and embeddings (extends M2/M4/M5):**
- New `resumes.extracted_text` column (migration `dd04e5b9a3c2`) — populated by the parse worker so per-candidate Ask and the embedding builder both see the *full* resume body, not just the LLM's parsed `summary`. Fixed a class of bug where techs mentioned in prose (project descriptions, work history) couldn't be retrieved.
- Shared helper `app/services/resume_text.py:get_resume_text` — `extracted_text` > re-extract from S3 > `parsed_json["summary"]` fallback chain. Used by both consumers.
- `build_document` now caps the resume slice at `MAX_RESUME_CHARS=6000` so a freakishly long resume can't dominate the embed budget.

**Duplicate detection (extends M1):**
- `GET /candidates/{id}/duplicates` — returns active candidates matching by `lower(email)` or exact `phone`, excluding self and soft-deleted. Computed on demand (no new column).
- Candidate detail page shows an amber banner when matches exist. Detection happens post-parse: bulk-import can't know identity at upload time because parsing is async.

**Better pool-Q&A ranking UX (extends M5):**
- `_semantic_pick` returns up to `SEMANTIC_LIMIT=50` ranked candidates (was 10). Synthesis still uses top `SYNTHESIS_TOP_K=10` so the LLM call stays focused.
- Each citation carries `score` (raw cosine) and `percentile` (rank within the filtered pool, 0–100, 100 = best match). The UI displays the percentile because absolute cosine values vary wildly between embedding models — `text-embedding-3-small` and `voyage-3-large` cluster scores differently, but "top 5% of matches" reads the same regardless.

**Compose env passthrough fix (ops):**
- `LLM_QA_MODEL` was missing from `infra/docker-compose.yml`'s backend env block, so setting it in `.env` had no effect (containers fell back to `fake`). Fixed and added to `.env.example`.

**Admin bootstrap → CLI (ops):**
- Removed `BOOTSTRAP_ADMIN_*` env-based first-boot admin (and the lifespan hook that consumed it). Plaintext credentials in `.env` are a prod hazard.
- New CLI at `app/cli.py` with `admin create | set-password | list` subcommands; `make admin-create EMAIL=...`, `make admin-set-password EMAIL=...`, `make admin-list` wrappers. Interactive password prompt, echo-off, min 12 chars. Tests at `backend/tests/test_cli.py`.
