# Search (M4) and Ask (M5)

How the talent pool gets searched, and how Q&A across it will work.

This file covers M4 (search + embeddings) end-to-end. The "Ask" portion will be filled in during M5.

## What ships in M4

- `candidate_embeddings` table backed by **pgvector**, one row per candidate (`source='combined'` for now).
- `embed_candidate` Celery task that builds a per-candidate document and writes its embedding. Auto-fires when a resume parse completes; admin reindex hits everyone.
- `POST /search/candidates` endpoint that takes optional semantic `q` plus filter chips (`location`, `skills`, `exp_min`/`exp_max`, `stage_name`).
- `POST /admin/reindex/candidates` (admin only) — enqueues an embed task for every active candidate.
- A search-driven `/candidates` page with debounced live search and chip-based filters.

## The pipeline

```
candidate / resume parse / manual reindex
          │
          ▼
  embed_candidate (Celery task)
          │
   build_document(candidate) → "Asha Rao\nBackend Engineer\nPune\nSkills: Python, Postgres, FastAPI\n..."
          │
   embed(text)  ── via app/core/embeddings.py
          │            ├─ if LLM_EMBED_MODEL=fake → smart-fake (token-hash BoW)
          │            └─ else → LiteLLM → OpenAI/Voyage/etc.
          ▼
  candidate_embeddings: upsert (candidate_id, source='combined')
```

### What goes into the document

`app/services/embeddings.py:build_document` concatenates everything we know about the candidate that's worth retrieving on:

- `full_name`, `current_title`, `current_company`, `location`, `summary`
- `skills` (joined with commas)
- `total_exp_years`, `notice_period_days`
- The **full extracted text** of the primary resume (via `app/services/resume_text.py:get_resume_text`), capped at `MAX_RESUME_CHARS` (6000) so a freakishly long resume can't dominate the embedding budget. Fallback chain matches per-candidate Q&A: `extracted_text` > re-extract from object storage > `parsed_json["summary"]`.
- All **global** notes (`candidate_job_id IS NULL`)

Link-scoped notes (notes attached to a specific job) are excluded — they're commentary about a candidate's current placement, not signal we want to retrieve on across the whole pool.

> **Migrating existing data** — older candidates (uploaded when the embedding only contained `parsed_json["summary"]`) keep their stale vectors until you re-embed them. `POST /admin/reindex/candidates` re-runs `build_document` for every active candidate and refreshes the vector. With `text-embedding-3-small` that's one API call per candidate (≈ $0.02 / 1M tokens, so a few thousand candidates cost cents).

### When embeddings refresh

| Trigger | When |
|---|---|
| Resume parsed | Auto — `parse_resume` chains `embed_candidate.delay(candidate_id)` on success |
| Manual edit (`PATCH /candidates/{id}`) | **Not in M4** — admin reindex covers periodic refresh. Adding live re-embed on every PATCH is one line; we'll do it the moment it actually matters. |
| Note added/edited | Same as above |
| Admin reindex | `POST /admin/reindex/candidates` — fires an embed task for every active candidate |

## Switching to a real embedding model

You're not locked to any provider or dim. Switch in three steps:

```env
# infra/.env
LLM_EMBED_MODEL=openrouter/openai/text-embedding-3-small   # any LiteLLM-compatible id
LLM_EMBED_DIM=1536                                          # MUST match what the model returns
LLM_API_KEY=sk-or-v1-...                                    # or set OPENROUTER_API_KEY directly
```

Then:

```bash
make up                                                  # restart api/worker with the new env
curl -X POST 'http://localhost/api/admin/embeddings/reset?confirm=true' -b cookie.jar
```

`reset` does the right thing automatically:

1. Probes the configured embed model (one real embedding call) to discover the actual dim.
2. If `LLM_EMBED_DIM` doesn't match → returns `400` with a clear message. **No data is touched.**
3. If the dims match → drops `candidate_embeddings`, recreates at the new dim, rebuilds the `ivfflat` index, and enqueues an embed task per active candidate.

Pass `&skip_probe=true` if you're switching to `fake` mode or your model is temporarily unreachable.

### Common dims

| Model | Dim |
|---|---|
| `text-embedding-3-small`, `text-embedding-ada-002` | 1536 |
| `text-embedding-3-large` | 3072 |
| `voyage-3-large`, `cohere/embed-english-v3.0` | 1024 |
| `nomic-embed-text` (Ollama) | 768 |

If you don't know the dim, set `LLM_EMBED_DIM` to anything, call `reset` — the error message tells you the right value.

### Mixing providers

`LLM_API_KEY` is a single key. To use different providers per role (e.g. OpenRouter for parsing + OpenAI for embeddings), leave `LLM_API_KEY` unset and set the provider-specific env vars:

```env
LLM_PARSE_MODEL=openrouter/openai/gpt-4o-mini
LLM_EMBED_MODEL=text-embedding-3-small
OPENROUTER_API_KEY=sk-or-v1-...
OPENAI_API_KEY=sk-...
```

LiteLLM picks the right key based on the model prefix. The compose file passes through `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `COHERE_API_KEY` automatically.

## The smart-fake embedder

`LLM_EMBED_MODEL=fake` (the default) bypasses any real model. It tokenizes the document and assigns each token to ~8 deterministic dims with stable signs, then L2-normalizes the result. So:

- Same document → identical vector (deterministic)
- Documents that share tokens → higher cosine similarity than disjoint ones
- 1536-dim output (matches `text-embedding-3-small`, so swapping to a real model is just an env var)

It's not a substitute for a real model — there's no learned semantics, no synonyms, no multilingual handling. But it's good enough to demo end-to-end and to drive the test suite without API keys.

To use a real model, set in `infra/.env`:

```
LLM_EMBED_MODEL=text-embedding-3-small
LLM_API_KEY=sk-...
```

LiteLLM accepts any compatible id (Voyage, Cohere, local Ollama, etc.).

## The search endpoint

`POST /search/candidates`:

```json
{
  "q": "backend engineer with fintech experience",
  "location": "Pune",
  "skills": ["Python", "Postgres"],
  "exp_min": 3,
  "exp_max": 8,
  "stage_name": "Interested",
  "limit": 50,
  "offset": 0
}
```

All fields optional. Behavior:

- **No `q`** → filter-only path. Plain SQL with the supplied filters; results sorted by `created_at DESC`. `score` is `null`.
- **With `q`** → semantic path. Filters are applied to shrink the candidate set, then survivors are ranked by cosine distance against `candidate_embeddings.vector`. `score` is the cosine similarity (0–1).
- **`stage_name`** — matches candidates currently at any stage with this name on any job they're linked to. Useful for "show me everyone in Interested across all jobs."
- **`skills`** filter is an AND across the supplied tokens (each must appear in the candidate's skills array).

### How the SQL is built

On Postgres:

```sql
SELECT c.*, e.* FROM candidates c
JOIN candidate_embeddings e ON e.candidate_id = c.id AND e.source = 'combined'
WHERE c.deleted_at IS NULL
  AND <filter conditions>
ORDER BY e.vector <=> :qvec    -- pgvector cosine distance, smaller = closer
LIMIT :limit OFFSET :offset;
```

The `<=>` operator uses the `ivfflat` index created by the M4 migration.

On SQLite (used in unit tests), the vector column is JSON. The same query runs without the `<=>` ordering; we rank in Python after fetching. Slow for thousands of rows; fine for small test fixtures.

## The frontend

`/candidates` is now search-driven:

- A single search bar at the top. Free-text query.
- Filter chips below: location, skills (Enter to add), experience min/max, stage dropdown.
- Debounced (250ms) refetch on any change — no submit button needed.
- Each result card shows the candidate's name, current role/company/location, a few skills, and (when there's a query) the cosine score as a percentage.
- An admin-only "Reindex pool" button that hits `/admin/reindex/candidates`.

## Live-system check

The live smoke test for M4 (run during the milestone build):

```
== query: "application support ITIL technical lead PMP" ==
  AMIT MALVI         score=0.5567   ← resume actually contains these tokens
  Different Name     score=0.0127

== filter intersection: q="engineer" + location=Bangalore ==
  Different Name     score=0.0719   ← only candidate in Bangalore
```

The fake embedder ranks the right candidate ~40× higher than the unrelated one. Filters intersect with semantic ranking exactly as designed.

## Why these choices

- **Single combined source per candidate.** Plan mentions per-source rows; we may split if recall suffers. Keeping M4 simple.
- **`ivfflat` over HNSW.** Smaller memory footprint, easy to reason about; HNSW is a single migration away if we outgrow it.
- **Smart-fake by default.** The thing the user demos works with zero setup. Real models are one env var away.
- **`VectorColumn` TypeDecorator.** Vector on Postgres, JSON on SQLite — same model file works in both contexts. Vector ops (`<=>`) only exist on Postgres; SQLite ranks in Python.
- **No live re-embed on every PATCH.** Easy to add; not worth the write amplification until we see freshness drift in practice. Admin reindex covers periodic refresh.

## Code map

| Concern | File |
|---|---|
| Vector column type | `app/core/vector_type.py` |
| Embedder | `app/core/embeddings.py` |
| Document builder + upsert | `app/services/embeddings.py` |
| Embed task | `app/workers/tasks/embed_candidate.py` |
| Resume → embed chain | `app/workers/tasks/parse_resume.py` (tail) |
| Search service | `app/services/search.py` |
| Search API | `app/api/search.py` |
| Admin reindex | `app/api/admin.py` |
| Migration | `alembic/versions/aa01_m4_*.py` |
| Tests | `backend/tests/test_embeddings.py`, `tests/test_search.py` |
| Search UI | `frontend/app/(app)/candidates/page.tsx` + `search-client.tsx` |

## M5 — Ask

Two endpoints, both POST, both auth-cookie:

| Path | What it does |
|---|---|
| `/ask/candidate/{id}` | RAG over one candidate's profile + primary resume + all notes. Returns `{answer, citations}`. |
| `/ask/pool` | Routed Q&A across the whole pool. Returns `{answer, route, citations, rows?, matched_count}`. |

### Per-candidate Q&A

`app/services/qa_candidate.py` builds a context block per candidate:

```
[PROFILE]   Name / Email / Phone / Location / Title / Company / Exp / CTC / Notice / Skills / Summary
[RESUME #<id>]  <parsed resume text>
[NOTE #<id> · global|link]   <note body>
... (one block per note, newest first)
```

That whole block + the question goes to the configured Q&A model. The model is told to *cite by bracket tag* (e.g. `[NOTE #12]`). The endpoint returns the answer plus a citation list pre-built from the source rows so the UI can link straight to each source.

`fake` mode: extracts ≥4-letter keywords from the question, returns the matching context lines. Deterministic; good enough to demo without an API key.

### Pool Q&A — the SQL-routed path

The plan called this "the part where the user asks a question across the whole pool, and the system has to decide HOW to answer it." Three routes:

| Route | Trigger pattern | What runs |
|---|---|---|
| `structured` | counts/filters/aggregations ("how many Python devs in Pune", "candidates in each stage") | classifier → LLM emits a `StructuredQuery` (Pydantic) → translator → SQL on `v_candidate_search` → synthesizer |
| `semantic` | fuzzy/qualitative ("backend engineer with fintech experience") | classifier → vector search (M4) → top-k candidates → synthesizer |
| `hybrid` | filter + fuzzy together | classifier → both: structured filters constrain the candidate set, semantic ranks survivors |

The classifier is one small JSON-mode LLM call. In `fake` mode, it's regex over the question.

**Result sizing for semantic / hybrid**: `_semantic_pick` returns up to `SEMANTIC_LIMIT` (50) ranked candidates so recruiters can browse beyond just the top few. The synthesis call (the narrative `answer`) only reads the top `SYNTHESIS_TOP_K` (10) — keeps the LLM call focused and cheap.

**Percentile vs. cosine score**: Each citation carries both `score` (raw cosine similarity, 0–1) and `percentile` (rank within the filtered pool, 0–100, 100 = best match). The UI shows the percentile because absolute cosine similarity varies wildly between embedding models — `text-embedding-3-small` clusters scores differently from `voyage-3-large` — and "this candidate is in the top 5% of matches for your query" is a more honest read than "0.78 cosine". The cosine score is still surfaced via the badge tooltip for anyone who wants to inspect it. Formula: `(pool_size - rank + 1) / pool_size * 100`. The pool size respects hybrid filters: a query like "Python devs in Pune" computes percentile relative to other Python-Pune candidates only.

### The safety boundary

> **The LLM never emits SQL. It emits a Pydantic-shaped `StructuredQuery`.**

```python
class StructuredQuery(BaseModel):
    aggregate: Literal["count", "list"]
    filters: list[FilterClause] = []
    select: list[Literal[ALLOWED_COLUMNS]] = []
    group_by: Literal[ALLOWED_COLUMNS] | None = None
    order_by: Literal[ALLOWED_COLUMNS] | None = None
    desc: bool = False
    limit: int = Field(default=50, ge=1, le=500)

class FilterClause(BaseModel):
    column: Literal[ALLOWED_COLUMNS]
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte",
                "ilike", "is_null", "not_null", "contains_skill", "in"]
    value: Any = None
```

`ALLOWED_COLUMNS` is hard-coded in `app/services/qa_pool_query.py` and matches the columns of `v_candidate_search`. The view itself is **read-only** — no `users`, no `audit_log`, no resume content. The query compiler translates `StructuredQuery` into a parameterized `SELECT … FROM v_candidate_search` with bound parameters. Free-form SQL has no path into the database.

13 tests in `tests/test_qa_pool_query.py` lock down the safety properties: unknown column → Pydantic rejects, unknown op → Pydantic rejects, op missing required value → Pydantic rejects, `limit > 500` → Pydantic rejects, etc.

### `v_candidate_search`

The view (created by migration `bb02d6f3a8e1`) flattens everything the pool Q&A needs:

| Column | Source |
|---|---|
| `candidate_id`, `full_name`, `email`, `phone`, `location` | `candidates.*` |
| `current_company`, `current_title`, `total_exp_years`, `current_ctc`, `expected_ctc`, `notice_period_days` | `candidates.*` |
| `skills`, `summary`, `created_at` | `candidates.*` |
| `current_stage_name`, `current_job_title` | most recent `candidate_jobs` link → `job_stages` / `jobs` |
| `active_link_count` | count of `candidate_jobs` rows |
| `resume_count`, `note_count` | counts |

Soft-deleted candidates are excluded by the view itself (`WHERE c.deleted_at IS NULL`), so the LLM can't accidentally surface them.

### Adding a new column to the view

1. Edit the `VIEW_SQL` in the migration (or write a new migration that does `CREATE OR REPLACE VIEW`).
2. Add the column name to `ALLOWED_COLUMNS` in `app/services/qa_pool_query.py`.
3. Update the `_SQLGEN_SYSTEM` prompt in `app/services/qa_pool.py` so the LLM knows the column exists.

### `fake` mode

`LLM_QA_MODEL=fake` (the default) covers all three Q&A roles — classifier, SQL gen, synthesis — with deterministic regex/keyword logic. So the entire Q&A surface works end-to-end without an API key. To switch to a real model:

```env
LLM_QA_MODEL=openrouter/openai/gpt-4o-mini   # or any LiteLLM-compatible id
```

`make up` — no DB reset needed.

### Code map

| Concern | File |
|---|---|
| Per-candidate Q&A service | `app/services/qa_candidate.py` |
| Pool dispatch (classifier / SQL gen / synthesis) | `app/services/qa_pool.py` |
| StructuredQuery + safe SQL builder | `app/services/qa_pool_query.py` |
| Endpoints | `app/api/ask.py` |
| LLM chat helpers | `app/core/llm.py` |
| View migration | `alembic/versions/bb02_m5_v_candidate_search_view.py` |
| Per-candidate UI | `frontend/app/(app)/candidates/[id]/ask.tsx` |
| Pool UI | `frontend/app/(app)/ask/page.tsx` + `pool-ask.tsx` |
| Tests | `backend/tests/test_ask_candidate.py`, `test_qa_pool_query.py`, `test_ask_pool.py` |

### What's NOT in M5 (deferred)

- **Streaming responses** — plan calls for it; deferred as polish. The endpoints return whole answers today. `StreamingResponse` server-side + fetch-stream client-side is a small follow-up.
- **Per-role models** — one env var (`LLM_QA_MODEL`) covers classifier + SQL gen + synthesis. Splitting per role is straightforward when needed.
- **Conversation history / multi-turn** — every call is independent.
- **Q&A audit log** — M6 territory.
- **Result caching** — every call hits the model fresh; LRU is easy to add later.
