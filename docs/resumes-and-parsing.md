# Resumes & parsing

How resume upload, storage, and parsing fit together — and why the sticky-edit invariant is the keystone of this milestone.

## The pipeline

```
upload → API → object storage (MinIO/R2)
            └→ DB row (parse_status=pending)
            └→ Celery task on Redis
                  └→ worker pulls bytes
                       └→ pypdf / python-docx → text
                            └→ LiteLLM → parsed JSON (Pydantic-shaped)
                                 └→ apply_parsed_fields(candidate, parsed)
                                       (skips fields in candidate_field_overrides)
                                 └→ resume.parse_status = "done"
```

`parse_status` transitions: `pending` → `parsing` → `done` | `failed`.

The whole pipeline is async — the upload API responds the moment the row + S3 object exist. The worker handles the rest. The frontend polls the resume list every 1.5s while anything is in `pending`/`parsing`.

## Storage

We use **MinIO** in dev (a container in `infra/docker-compose.yml`) and **Cloudflare R2** in prod. Both speak S3, so the same boto3 client works against either; only env vars change.

| Env var | Purpose |
|---|---|
| `S3_ENDPOINT` | What the api/worker call (internal compose URL in dev: `http://minio:9000`). |
| `S3_PUBLIC_ENDPOINT` | What goes into pre-signed download URLs the **browser** receives. Defaults to `http://localhost:9000` in dev. |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Credentials. Defaults are MinIO's hardcoded dev values; **change these in prod**. |
| `S3_BUCKET` | Bucket name. The compose `minio-init` job creates it on first boot. |
| `S3_REGION` | R2 needs `auto`; MinIO accepts anything; we default to `us-east-1`. |

Resume objects are stored at:

```
resumes/{candidate_id}/{uuid}.pdf|.docx
```

## The LLM layer

All LLM calls go through `app/core/llm.py`, a thin LiteLLM wrapper. Each task picks its model via env var — `LLM_PARSE_MODEL` for resume parsing today, more roles to come.

### Default: `fake`

`LLM_PARSE_MODEL=fake` (the dev default) bypasses any real model and runs a small regex-based parser. Useful because:

- No API key required for local dev
- Tests don't need to mock anything LLM-related
- The full pipeline (upload → S3 → worker → fields applied) runs end-to-end with deterministic output

The fake parser pulls a name from the first non-empty line, an email by regex, and skills from anything that looks like a `Skills: a, b, c` line. Everything else is `null`.

### Real parsing

Set `LLM_PARSE_MODEL=gpt-4o-mini` (or any LiteLLM-compatible id — e.g. `anthropic/claude-haiku-4-5`, `groq/llama-3.3-70b`) and `LLM_API_KEY` in `infra/.env`. LiteLLM routes from there. The prompt is in `app/core/llm.py:PARSE_PROMPT` and uses JSON-mode response.

## The sticky-edit invariant — the rule that keeps human edits safe

> **Manual edits to candidate fields are sticky. Re-parsing a resume — including a brand-new resume — never overwrites a human edit.**

Implementation:

1. `candidate_field_overrides` is a `(candidate_id, field_name)` table.
2. `PATCH /candidates/{id}` writes one row per changed field via `apply_manual_edit`.
3. When the parser tries to apply a field, `apply_parsed_fields` first reads the override set and **skips any field already in there**.
4. Both call paths live in `app/services/candidates.py`, so the rule cannot be bypassed by writing a different endpoint.

We also skip `None` and empty-list parsed values so a flaky parse can never **blank** a previously good value.

Verified by:
- `tests/test_sticky_overrides.py` (5 cases)
- `tests/test_resumes.py::test_manual_edit_is_sticky_through_reparse`
- Live smoke test in this milestone: manually set `location=Bangalore`, then uploaded a resume containing "Location: Pune" — `location` stayed `Bangalore` while the un-overridden `full_name` and `skills` updated correctly.

## API surface

| Method | Path | Body | Notes |
|---|---|---|---|
| `POST`   | `/candidates/{id}/resumes` | multipart `file` (PDF/DOCX, ≤10 MB) | Returns the row in `pending` status; first upload becomes primary |
| `GET`    | `/candidates/{id}/resumes` | — | Sorted: primary first, then newest |
| `POST`   | `/resumes/{id}/primary` | — | Demotes others on the same candidate |
| `POST`   | `/resumes/{id}/reparse` | — | Resets to `pending`, re-enqueues |
| `DELETE` | `/resumes/{id}` | — | Removes object and row; promotes the next-newest to primary |
| `GET`    | `/resumes/{id}/url` | — | Returns `{url, expires_in}` — pre-signed URL valid for 5 minutes |

## Failure modes

- **Upload of an unsupported MIME** → `415`. Allowed: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/msword`.
- **Resume larger than 10 MB** → `413`.
- **PDF/DOCX text extraction fails** → falls back to UTF-8 decode of the raw bytes. Better than failing the whole pipeline; the LLM is robust to noise.
- **LLM call raises** → `parse_status=failed`, `parse_error` populated with traceback head. Celery retries up to 2× with a 15s backoff before giving up.

## Why this shape

- **Sticky-edit logic in a service module, not in the route handler.** Keeps the rule visible and testable. If a future endpoint also writes candidate fields, it must go through `apply_manual_edit` — that's the contract.
- **Fake-parse mode**, not pure mocking. Tests use it; dev uses it. The real LLM path is exercised the moment you set a real model.
- **Same boto3 client for MinIO and R2.** No abstraction layer to maintain — it's just S3 + an env var.
- **Per-task LLM env vars from the start.** When M4–M5 need different models for embeddings and SQL gen, the wrapper is already shaped for that.

## Code map

| Concern | File |
|---|---|
| Resume model | `app/models/resume.py` |
| Field overrides model | `app/models/resume.py` (same file) |
| Storage wrapper | `app/core/storage.py` |
| LLM wrapper | `app/core/llm.py` |
| Candidate write rules | `app/services/candidates.py` |
| Text extraction | `app/services/parsing.py` |
| Resume API | `app/api/resumes.py` |
| Celery app | `app/workers/celery_app.py` |
| Parser task | `app/workers/tasks/parse_resume.py` |
| Resume UI | `frontend/app/(app)/candidates/[id]/resumes.tsx` |
| Upload + status badges | same file |
| Tests | `backend/tests/test_resumes.py`, `tests/test_sticky_overrides.py` |
