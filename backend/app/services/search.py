"""Candidate search.

Two paths:
1. **Filter-only** (no `q`) — plain SQL with the supplied filters.
2. **Semantic** — embed `q` and rank by cosine distance against
   `candidate_embeddings`. Filters are applied in the same SQL query so
   they shrink the candidate set before vector ranking.

The vector path requires Postgres + pgvector. The filter path works on any
backend (SQLite tests use it).
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.embeddings import embed
from app.models.candidate import Candidate
from app.models.embedding import CandidateEmbedding
from app.models.job import JobStage
from app.models.pipeline import CandidateJob
from app.schemas.search import SearchRequest


def _filters(req: SearchRequest):
    conds: list[Any] = [Candidate.deleted_at.is_(None)]
    if req.location:
        conds.append(Candidate.location.ilike(f"%{req.location}%"))
    if req.exp_min is not None:
        conds.append(Candidate.total_exp_years >= req.exp_min)
    if req.exp_max is not None:
        conds.append(Candidate.total_exp_years <= req.exp_max)
    if req.skills:
        # Skills are stored as JSON. We do a simple "any of these tokens
        # appears in the JSON serialization" filter — not perfect, but works
        # on both Postgres and SQLite without a special index. M5 may switch
        # to GIN containment queries on Postgres only.
        for s in req.skills:
            conds.append(
                func.lower(func.cast(Candidate.skills, type_=__import__("sqlalchemy").String)).like(
                    f"%{s.lower()}%"
                )
            )
    return conds


def _stage_subquery(req: SearchRequest):
    """Return an EXISTS subquery for "candidate is currently at a stage named X
    on some job". Returns None when stage_name isn't set.
    """
    if not req.stage_name:
        return None
    return (
        select(CandidateJob.candidate_id)
        .join(JobStage, JobStage.id == CandidateJob.current_stage_id)
        .where(
            CandidateJob.candidate_id == Candidate.id,
            func.lower(JobStage.name) == req.stage_name.lower(),
        )
        .exists()
    )


def filter_only(
    db: Session,
    req: SearchRequest,
    *,
    visible_ids: Select | None = None,
) -> list[tuple[Candidate, float | None]]:
    stmt = select(Candidate).where(*_filters(req))
    sub = _stage_subquery(req)
    if sub is not None:
        stmt = stmt.where(sub)
    if visible_ids is not None:
        stmt = stmt.where(Candidate.id.in_(visible_ids))
    stmt = stmt.order_by(Candidate.created_at.desc()).offset(req.offset).limit(req.limit)
    return [(c, None) for c in db.scalars(stmt).all()]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Vectors stored in our DB are L2-normalized, so this
    reduces to a dot product, but we don't rely on that here."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic(
    db: Session,
    req: SearchRequest,
    *,
    visible_ids: Select | None = None,
) -> list[tuple[Candidate, float | None]]:
    """Filter the candidate set by hard filters, then rank by cosine distance.

    On Postgres + pgvector this uses the `<=>` operator (cosine distance) and
    pgvector's index. On SQLite the embedding column is JSON and we rank
    in Python — slow for many rows but fine for tests.
    """
    assert req.q is not None
    qvec = embed(req.q)

    base = select(Candidate, CandidateEmbedding).join(
        CandidateEmbedding,
        CandidateEmbedding.candidate_id == Candidate.id,
    ).where(*_filters(req), CandidateEmbedding.source == "combined")
    sub = _stage_subquery(req)
    if sub is not None:
        base = base.where(sub)
    if visible_ids is not None:
        base = base.where(Candidate.id.in_(visible_ids))

    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect == "postgresql":
        # pgvector's `<=>` is cosine distance (smaller = more similar).
        # We bind the vector as a `[a,b,...]`-formatted string and let
        # Postgres cast it to `vector(1536)` so the ivfflat index can be used.
        from sqlalchemy import text

        qvec_str = "[" + ",".join(str(x) for x in qvec) + "]"
        order = text("candidate_embeddings.vector <=> :qvec")
        base = base.order_by(order).limit(req.limit).offset(req.offset)
        rows = db.execute(base, {"qvec": qvec_str}).all()
        out: list[tuple[Candidate, float | None]] = []
        for cand, emb in rows:
            score = _cosine(qvec, list(emb.vector))
            out.append((cand, score))
        return out

    # Fallback: rank in Python (sqlite tests path)
    rows = db.execute(base).all()
    scored = [(c, e, _cosine(qvec, list(e.vector))) for c, e in rows]
    scored.sort(key=lambda r: r[2], reverse=True)
    page = scored[req.offset : req.offset + req.limit]
    return [(c, score) for c, _emb, score in page]


def search(
    db: Session,
    req: SearchRequest,
    *,
    visible_ids: Select | None = None,
) -> list[tuple[Candidate, float | None]]:
    if req.q and req.q.strip():
        return semantic(db, req, visible_ids=visible_ids)
    return filter_only(db, req, visible_ids=visible_ids)


def count(db: Session, req: SearchRequest, *, visible_ids: Select | None = None) -> int:
    """Total candidates that match these filters, ignoring limit/offset.

    When `q` is set we count candidates that have an embedding (the inner
    join the semantic path uses), so the result reflects the same pool
    semantic ranking actually saw — which is what percentile computation
    needs.
    """
    if req.q and req.q.strip():
        stmt = (
            select(func.count())
            .select_from(Candidate)
            .join(
                CandidateEmbedding,
                CandidateEmbedding.candidate_id == Candidate.id,
            )
            .where(*_filters(req), CandidateEmbedding.source == "combined")
        )
    else:
        stmt = select(func.count()).select_from(Candidate).where(*_filters(req))
    sub = _stage_subquery(req)
    if sub is not None:
        stmt = stmt.where(sub)
    if visible_ids is not None:
        stmt = stmt.where(Candidate.id.in_(visible_ids))
    return int(db.scalar(stmt) or 0)
