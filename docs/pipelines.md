# Pipelines, kanban, and audit

How candidates move through stages on a job, what's permanent vs ephemeral, and where each piece lives in the code.

## The shape

```
candidate ─┐
           │  links  ┌────────────────────────┐
job ───────┴────────►│ candidate_jobs         │  ephemeral: holds the
                     │   current_stage_id     │  current stage only
                     └────────────────────────┘
                                │
                                │ every change writes one row →
                                ▼
                     ┌────────────────────────┐
                     │ stage_transitions      │  permanent audit:
                     │   from_stage_id, to    │  one row per move,
                     │   by_user, at          │  including link & unlink.
                     └────────────────────────┘
```

Two tables, one rule:

> **The audit is permanent. Unlinking a candidate from a job removes the `candidate_jobs` row but the `stage_transitions` rows stay forever.**

This is the keystone invariant of M3 and the reason the audit table doesn't have a foreign key back to `candidate_jobs` — that link would force the audit rows to be cascaded away on unlink, exactly what we don't want.

## Lifecycle of a link

| Event | What changes in `candidate_jobs` | What's written to `stage_transitions` |
|---|---|---|
| **Link** (candidate added to a job) | row inserted at stage 0 | one row, `from_stage_id=NULL`, `to_stage_id=<stage_0>` |
| **Move** (drag to another column) | `current_stage_id` updated | one row, `from_stage_id=<old>`, `to_stage_id=<new>` |
| **Move to same stage** | no-op | nothing written (idempotent) |
| **Unlink** | row deleted | one row, `from_stage_id=<last>`, `to_stage_id=NULL` (the "left the pipeline" marker) |
| **Re-link** after unlink | new row at stage 0 | new "first" transition row |

Every state change goes through `app/services/pipeline.py`, which writes the audit row in the same DB transaction as the candidate-jobs change. The two cannot drift.

## API surface

### On a job

| Method | Path | Notes |
|---|---|---|
| `GET`  | `/jobs/{id}/board` | Stages with their links (each link includes the embedded candidate). Soft-deleted candidates are filtered out. |
| `POST` | `/jobs/{id}/candidates` | `{candidate_id}` — link a candidate. Auto-placed at stage 0. `409` if already linked. |

### On a link

| Method | Path | Notes |
|---|---|---|
| `PATCH`  | `/candidate-jobs/{id}` | `{stage_id}` — move. Stage must belong to the same job; cross-job moves return `400`. |
| `DELETE` | `/candidate-jobs/{id}` | Unlink (writes the final `to=NULL` audit row). |
| `GET`    | `/candidate-jobs/{id}/transitions` | Full history for this link. |
| `GET`    | `/candidate-jobs/{id}/notes` | List link-scoped notes. |
| `POST`   | `/candidate-jobs/{id}/notes` | Add a link-scoped note. |

### Notes scope reminder

`notes` rows now have a nullable `candidate_job_id`:

| `candidate_job_id` | Meaning |
|---|---|
| `NULL` | Global note about the candidate (the M1 default). Listed on the candidate detail page and via `GET /candidates/{id}/notes`. |
| set | Note attached to one specific link. Listed on the kanban drawer for that card and via `GET /candidate-jobs/{id}/notes`. |

`GET /candidates/{id}/notes` returns **both** scopes — every note about that candidate, regardless of whether it's tied to a specific job. The link-scoped endpoint is the way to filter to a single job.

## Frontend kanban

`app/(app)/jobs/[id]/board.tsx` is the drag-and-drop board (built on `@dnd-kit/core`):

- One column per `job_stages` row, in `position` order.
- Cards drag between columns. **Optimistic update** moves the row in local state immediately, then rolls back if the API rejects.
- A card's `details` button (visible on hover) opens a right-side drawer with that link's full transition history and link-scoped notes (`app/(app)/jobs/[id]/link-drawer.tsx`).
- Linking a candidate uses a searchable picker (`link-candidate-button.tsx`) that filters the entire pool client-side. (M4's real search will replace this.)
- Re-fetches happen via `router.refresh()` after each successful move/unlink so dependent server components (e.g. the dashboard) stay in sync.

## Why these choices

- **No FK from `stage_transitions` to `candidate_jobs`.** A FK would have to cascade on unlink; we want the opposite — audit must outlive the link.
- **Re-link creates a fresh row, not a revival.** Simpler model, easier to reason about. The history is searchable by `(candidate_id, job_id)` so reading "everything that ever happened" still works.
- **Same-stage move is a no-op.** No noise in the audit log; drag-back-to-same-column is a common pattern.
- **`to_stage_id=NULL` as the unlink marker.** Discoverable by reading the audit table directly — no need for a separate `events` enum.
- **Optimistic UI with rollback on the kanban.** Drags felt sluggish without it; rollback keeps users honest if a 4xx slips out (e.g. a stage that was deleted from a different tab).
- **`@dnd-kit/core`** rather than `react-beautiful-dnd` — actively maintained, hooks-first, smaller bundle.

## Code map

| Concern | File |
|---|---|
| Models | `app/models/pipeline.py` |
| Service (audit invariant lives here) | `app/services/pipeline.py` |
| Pipeline API (jobs side + per-link side) | `app/api/pipeline.py` |
| Link-scoped notes endpoints | `app/api/notes.py` (bottom of file) |
| Migration | `alembic/versions/75afa9bfaebf_m3_*.py` |
| Tests (audit invariant + 10 others) | `backend/tests/test_pipeline.py` |
| Kanban UI | `frontend/app/(app)/jobs/[id]/board.tsx` |
| Picker | `frontend/app/(app)/jobs/[id]/link-candidate-button.tsx` |
| Drawer (history + link notes) | `frontend/app/(app)/jobs/[id]/link-drawer.tsx` |
