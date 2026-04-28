# Data model

What's in the database, why, and what stays invariant. Updated as new milestones add tables.

## Current schema (M1)

```
users                                      stage_templates
├── id                                     ├── id
├── email (unique)                         ├── name
├── name                                   └── position
├── password_hash (argon2)
├── role  (admin | recruiter)
├── must_change_password                   clients
├── is_active                              ├── id
└── created_at                             ├── name
                                           ├── notes
                                           └── created_at
candidates
├── id                                     jobs
├── full_name                              ├── id
├── email                                  ├── client_id  → clients (RESTRICT)
├── phone                                  ├── title
├── location                               ├── jd_text
├── current_company                        ├── location
├── current_title                          ├── exp_min, exp_max
├── total_exp_years                        ├── ctc_min, ctc_max
├── current_ctc                            ├── status (open|on-hold|closed)
├── expected_ctc                           ├── created_by → users (SET NULL)
├── notice_period_days                     └── created_at
├── skills (JSON list[str])
├── summary                                job_stages
├── deleted_at  (NULL = active)            ├── id
└── created_at                             ├── job_id  → jobs (CASCADE)
                                           ├── name
notes                                      └── position
├── id
├── candidate_id → candidates (CASCADE)
├── author_id    → users (SET NULL)
├── body
└── created_at
```

## Invariants (the rules the app guarantees)

1. **There is always exactly one bootstrap admin from env on first boot.** After that, only an admin can create users (M0).
2. **The default stage template is seeded once.** Eight stages from the plan, in the documented order. The seed runs on lifespan and is idempotent.
3. **Per-job stages are independent of the template.** When a job is created, the current `stage_templates` rows are deep-copied into `job_stages`. Editing the template afterwards does not retroactively alter existing jobs. (Verified by tests.)
4. **A client cannot be deleted while it has jobs.** API returns `409 Conflict`. Deleting a job cascades to its `job_stages`.
5. **Candidate deletes are soft.** `deleted_at` is set; the row stays. Default `GET /candidates` and `GET /candidates/{id}` exclude soft-deleted rows; `?include_deleted=true` and `POST /candidates/{id}/restore` are the explicit paths back in.
6. **Notes belong to a candidate.** Edit/delete is restricted to the author or an admin. M3 will introduce job-link-scoped notes by adding a nullable `candidate_job_id`.

## Why these choices

- **`skills` as JSON, not Postgres ARRAY** — works on both Postgres (jsonb) and SQLite (used in tests). The data shape is identical from app code's perspective. Switching to `text[]` later is a one-line migration if we ever need GIN-indexed array containment.
- **No `created_by` on clients/candidates** — the plan doesn't require it and we don't want to back-fill `null`s when running the migration on existing data later. Notes and jobs do track `created_by` because attribution matters there.
- **`ON DELETE` policies are explicit** — `RESTRICT` for client→jobs (forces a deliberate close), `CASCADE` for job→job_stages and candidate→notes (the children make no sense without their parent), `SET NULL` for user references (we don't want a deactivated recruiter to vacuum out their notes).
- **Numerics use `Numeric(p,s)`, not `float`** — CTC and experience hold money/time and shouldn't drift in binary float.

## Migrations so far

| Revision | Title | What it adds |
|---|---|---|
| `9384ac604c42` | baseline users | `users` |
| `a9b9b6f3d3ac` | m1 clients jobs candidates notes stage templates | `clients`, `jobs`, `job_stages`, `candidates`, `notes`, `stage_templates` |
| `3ff08e5c873b` | m2 resumes and field overrides | `resumes`, `candidate_field_overrides` |
| `75afa9bfaebf` | m3 candidate_jobs and stage_transitions | `candidate_jobs`, `stage_transitions`, `notes.candidate_job_id` (nullable) |
| `aa01c8e2f4d6` | m4 candidate_embeddings pgvector | enables `vector` extension; `candidate_embeddings` (with `ivfflat` index on Postgres, JSON column on SQLite) |
| `bb02d6f3a8e1` | m5 v_candidate_search view | read-only `v_candidate_search` view (Postgres only) — the only surface the pool-Q&A SQL path can read |
| `cc03e9a4b2f7` | m6 audit_log | `audit_log` table — operational write-side event log |

## M2 additions

### `resumes`

| col | type | note |
|---|---|---|
| `id` | int PK | |
| `candidate_id` | FK → candidates (CASCADE) | indexed |
| `filename`, `s3_key`, `mime` | string | original name, where it lives in S3, content type |
| `is_primary` | bool | exactly one per candidate; first upload wins by default |
| `parse_status` | string | `pending` → `parsing` → `done` \| `failed` |
| `parse_error` | string \| null | head of traceback if failed |
| `parsed_json` | json \| null | the LLM's raw structured output, kept for debugging/replay |
| `created_at` | timestamp | |

### `candidate_field_overrides`

The "manual edits are sticky" invariant materialized:

| col | type | note |
|---|---|---|
| `(candidate_id, field_name)` | composite PK | one row per overridden field |
| `set_by` | FK → users (SET NULL) | who edited last |
| `set_at` | timestamp | when |

`PATCH /candidates/{id}` writes a row per changed field. The parser reads this set and skips any field present in it. See [resumes-and-parsing.md](./resumes-and-parsing.md) for the full rationale.

## M3 additions

### `candidate_jobs` — the "this person is on this job" link

| col | type | note |
|---|---|---|
| `id` | int PK | |
| `candidate_id` | FK → candidates (CASCADE) | indexed |
| `job_id` | FK → jobs (CASCADE) | indexed |
| `current_stage_id` | FK → job_stages (RESTRICT) | the **current** stage; history lives elsewhere |
| `linked_at` | timestamp | |
| unique `(candidate_id, job_id)` | | one active link per pair |

### `stage_transitions` — permanent audit

| col | type | note |
|---|---|---|
| `id` | int PK | |
| `candidate_id` | FK → candidates (CASCADE) | indexed |
| `job_id` | FK → jobs (CASCADE) | indexed |
| `from_stage_id` | FK → job_stages (SET NULL) \| null | NULL on the initial link row |
| `to_stage_id` | FK → job_stages (SET NULL) \| null | NULL on the unlink-marker row |
| `by_user` | FK → users (SET NULL) | who moved them |
| `at` | timestamp | |

Notably **no FK to `candidate_jobs`** — that would cascade away the audit trail when a link is removed, which is exactly what we don't want. The audit table lives independently and outlives unlinks.

### `notes.candidate_job_id`

New nullable column. `NULL` = global note about the candidate (the M1 default). Set = note attached to one specific candidate–job link, used for stage-specific commentary on the kanban.

## M4 additions

### `candidate_embeddings`

| col | type | note |
|---|---|---|
| `id` | int PK | |
| `candidate_id` | FK → candidates (CASCADE) | indexed |
| `source` | string | `combined` for now; future split could be `resume`, `notes`, `profile` |
| `content` | text | the document we embedded — kept for debugging/replay |
| `vector` | `vector(1536)` on PG, `JSON` on SQLite | L2-normalized output of the embed model |
| `updated_at` | timestamp | |
| unique `(candidate_id, source)` | | one row per source per candidate |

Indexes (PG only): `ivfflat (vector vector_cosine_ops) WITH (lists=100)`. The `vector` extension itself is enabled by the migration via `CREATE EXTENSION IF NOT EXISTS vector`.

The `vector` column is a `VectorColumn` TypeDecorator (in `app/core/vector_type.py`) that uses pgvector's `Vector(1536)` on Postgres and falls back to `JSON` on other backends so SQLite-based unit tests can still create the table. ANN queries (`<=>`) only work on Postgres; the SQLite path ranks in Python.

To add a new model: edit `app/models/`, then `make makemigration m="describe it"`, **read the generated file**, adjust if needed, commit, `make migrate`.

## M5 additions

### `v_candidate_search` (view, Postgres only)

A read-only flat view that the pool-Q&A SQL path queries against. Includes everything from `candidates` (excluding soft-deleted rows) plus computed columns from the most recent `candidate_jobs` link (`current_stage_name`, `current_job_title`), and counts (`active_link_count`, `resume_count`, `note_count`).

**Lockstep contract**: the columns of this view match `ALLOWED_COLUMNS` in `app/services/qa_pool_query.py`. The whitelist is the safety boundary; the view shapes the data. Adding a column means editing both.

## M6 additions

### `audit_log`

Operational, best-effort write log. Not a security boundary — failures inserting rows here never fail the user's request.

| col | type | note |
|---|---|---|
| `id` | int PK | |
| `actor_id` | FK → users (SET NULL) | who performed the action |
| `action` | string(64) | dotted name e.g. `login`, `client.create`, `embeddings.reset` |
| `entity` | string(64) | model name (`user`, `client`, `candidate`, `system`, …) |
| `entity_id` | int \| null | the affected row's id (null for system-wide actions like reindex) |
| `payload` | jsonb \| null | small dict with extra context |
| `at` | timestamp | indexed |

Indexed on `actor_id`, `action`, `entity`, `entity_id`, `at`.

Wired into: login/logout, user create/update/reset-password, client/job/candidate create + delete, reindex/embeddings.reset. Note edits and per-field candidate PATCHes are intentionally NOT logged here — that's noise for an ops log; the `candidate_field_overrides` table already records per-field provenance.
