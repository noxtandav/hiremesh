# Resumes & parsing

How resume upload, storage, and parsing fit together — and why the sticky-edit invariant is the keystone of this milestone.

## The pipeline

```
upload → API → object storage (MinIO/R2)
            └→ DB row (parse_status=pending)
            └→ Celery task on Redis
                  └→ worker pulls bytes
                       └→ pypdf / python-docx → text
                            └→ stored on resume.extracted_text (powers Q&A)
                            └→ LiteLLM → parsed JSON (Pydantic-shaped)
                                 └→ apply_parsed_fields(candidate, parsed)
                                       (skips fields in candidate_field_overrides)
                                 └→ resume.parse_status = "done"
```

Per-candidate Q&A reads `extracted_text` directly so it can answer questions about anything that appears in the resume — not just the structured fields the parser lifted into `skills` / `summary`. For legacy uploads where the column is `NULL`, the Q&A path re-extracts from object storage on demand and falls back to `parsed_json["summary"]` if storage is unreachable.

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
| `POST`   | `/candidates/bulk-import` | multipart `files[]` (≤50 per batch) | Creates one candidate per file; per-file errors don't fail the batch |
| `GET`    | `/candidates/{id}/resumes` | — | Sorted: primary first, then newest |
| `POST`   | `/resumes/{id}/primary` | — | Demotes others on the same candidate |
| `POST`   | `/resumes/{id}/reparse` | — | Resets to `pending`, re-enqueues |
| `DELETE` | `/resumes/{id}` | — | Removes object and row; promotes the next-newest to primary |
| `GET`    | `/resumes/{id}/url` | — | Returns `{url, expires_in}` — pre-signed S3 download URL valid for 5 minutes |
| `GET`    | `/resumes/{id}/file` | — | Same-origin proxy: streams resume bytes through the API. Use `?download=true` to flip `Content-Disposition` to attachment. This is what the in-page PDF preview iframe and the download button hit — no need for `S3_PUBLIC_ENDPOINT` to be reachable from the user's browser. |

## In-page preview

The candidate detail page renders the primary resume inline using a same-origin iframe pointed at `/api/resumes/{id}/file#view=FitH` (the URL fragment tells the browser's PDF viewer to fit-to-width). DOCX/DOC fall back to a "Download" link since browsers can't render those formats natively. If a candidate has multiple resumes, a small toggle row above the iframe switches between them. Code: `frontend/app/(app)/candidates/[id]/resume-preview.tsx`.

## Adding candidates from a resume

Both the **New candidate** button and the **Bulk import** button on the candidates list page route through `POST /candidates/bulk-import`. New candidate is the single-file variant: drop one PDF/DOCX, get redirected to the new candidate's detail page; the parser fills name/skills/contact within seconds (the page polls every 1.5s while parsing). Bulk import takes many files at once and shows a per-file results list. Manual entry of a candidate without a resume is still available via the API (`POST /candidates`) but is not exposed in the UI today — every candidate created through the app starts from a resume.

## Duplicate detection

Bulk-import can't detect duplicates at upload time — parsing is async, so identity (email, phone) isn't known until the worker finishes. Detection happens **post-parse** via `GET /candidates/{id}/duplicates`, which returns active candidates that match the target's email (case-insensitive) or phone. The candidate detail page calls this and renders an amber banner if there are matches, so a recruiter sees the warning the next time they open the candidate. We don't auto-merge: the safer default is "surface and let a human decide".

## Bulk reparse (after changing the parse model)

`POST /admin/reparse/resumes` re-runs the parse pipeline on every resume in the database. Use it when you've switched `LLM_PARSE_MODEL` — new uploads pick up the new model immediately, but older candidates keep `parsed_json` extracted by the old one until a reparse rebuilds them.

The UX is two-step to avoid surprise bills:

1. First call (no params) → `{would_enqueue: N, warning: "..."}`. The admin button on `/admin/metrics` uses this to show "This will reparse N resumes — costs apply. Continue?"
2. Confirm call (`?confirm=true`) resets every resume's status to `pending`, clears any prior `parse_error`, and enqueues one `parse_resume` task per id.

Each parse task chains an `embed_candidate` task on success, so this also implicitly refreshes the embeddings — usually what you want, since changing the parse model also changes which structured fields end up on the candidate, which changes the document the embed model sees. Manual recruiter edits are preserved by the sticky-edit invariant: any field present in `candidate_field_overrides` is left untouched.

## Bulk import

`POST /candidates/bulk-import` is the multi-file variant of the upload flow. Each file becomes its own candidate with a placeholder name derived from the filename (`asha_rao.pdf` → `asha rao`). The parser overwrites that name when it runs — placeholders are never written to `candidate_field_overrides`, so the sticky-edit invariant is preserved (a parse result fills in the real `full_name` because there's no override).

Per-file errors (bad mime, oversize, empty) are reported in the response body without aborting the batch:

```json
{
  "imported": 2,
  "total": 3,
  "results": [
    {"filename": "asha.pdf", "status": "ok", "candidate_id": 17, "resume_id": 9, "placeholder_name": "asha"},
    {"filename": "notes.txt", "status": "error", "error": "Unsupported file type: text/plain"},
    {"filename": "ben.docx", "status": "ok", "candidate_id": 18, "resume_id": 10, "placeholder_name": "ben"}
  ]
}
```

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
