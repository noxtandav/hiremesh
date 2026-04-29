from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.models.audit import AuditLog
from app.models.candidate import Candidate
from app.models.client import Client
from app.models.embedding import EMBEDDING_DIM, CandidateEmbedding
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.services.audit import record as audit_record

router = APIRouter(prefix="/admin", tags=["admin"])


# ----- reindex / reset (M4) ---------------------------------------------


@router.post("/reindex/candidates")
def reindex_candidates(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Enqueue an embed task for every active candidate."""
    from app.workers.tasks.embed_candidate import embed_candidate

    ids = list(
        db.scalars(
            select(Candidate.id).where(Candidate.deleted_at.is_(None))
        ).all()
    )
    for cid in ids:
        embed_candidate.delay(cid)
    audit_record(
        db, actor_id=admin.id, action="reindex.candidates", entity="system",
        payload={"enqueued": len(ids)},
    )
    db.commit()
    return {"enqueued": len(ids)}


@router.post("/embeddings/reset")
def reset_embeddings(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    confirm: bool = False,
    skip_probe: bool = False,
):
    """Drop and recreate `candidate_embeddings` with the configured dim."""
    if not confirm:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Pass ?confirm=true to drop and recreate the embeddings table. "
            "All existing embeddings will be lost (a reindex is enqueued).",
        )

    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect != "postgresql":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Reset is only supported on Postgres; current dialect: {dialect}",
        )

    target_dim = EMBEDDING_DIM

    if not skip_probe:
        from app.core.embeddings import probe_dim

        try:
            actual = probe_dim()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Probe failed — could not call the configured embed model "
                f"({type(e).__name__}: {e}). Pass ?skip_probe=true to override.",
            ) from e
        if actual != target_dim:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Model returned {actual}-dim vectors but LLM_EMBED_DIM is "
                f"{target_dim}. Set LLM_EMBED_DIM={actual} in infra/.env, "
                f"`make up`, and try again.",
            )

    db.execute(text("DROP TABLE IF EXISTS candidate_embeddings CASCADE"))
    db.execute(text(f"""
        CREATE TABLE candidate_embeddings (
            id SERIAL PRIMARY KEY,
            candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            source VARCHAR(32) NOT NULL DEFAULT 'combined',
            content TEXT NOT NULL,
            vector vector({target_dim}) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    db.execute(text(
        "CREATE UNIQUE INDEX uq_candidate_embedding_source "
        "ON candidate_embeddings (candidate_id, source)"
    ))
    db.execute(text(
        "CREATE INDEX ix_candidate_embeddings_candidate_id "
        "ON candidate_embeddings (candidate_id)"
    ))
    db.execute(text(
        "CREATE INDEX ix_candidate_embeddings_vector "
        "ON candidate_embeddings USING ivfflat (vector vector_cosine_ops) "
        "WITH (lists = 100)"
    ))

    from app.workers.tasks.embed_candidate import embed_candidate

    ids = list(
        db.scalars(
            select(Candidate.id).where(Candidate.deleted_at.is_(None))
        ).all()
    )
    for cid in ids:
        embed_candidate.delay(cid)

    audit_record(
        db, actor_id=admin.id, action="embeddings.reset", entity="system",
        payload={"dim": target_dim, "enqueued": len(ids)},
    )
    db.commit()

    return {"reset": True, "dim": target_dim, "enqueued": len(ids)}


# ----- bulk reparse (post-M6) -------------------------------------------


@router.post("/reparse/resumes")
def reparse_all_resumes(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    confirm: bool = False,
):
    """Re-run the parse pipeline on every resume.

    Without `?confirm=true` this returns the count that *would* be processed,
    so the UI can show "this will reparse N resumes — costs apply" before
    actually enqueuing anything.

    With `?confirm=true`: reset every resume's `parse_status` to `pending`,
    clear `parse_error`, and enqueue a `parse_resume` task per id. Each task
    chains an `embed_candidate` task on success, so this also implicitly
    refreshes the candidate embeddings.

    Use after changing `LLM_PARSE_MODEL` — new uploads pick up the new model
    immediately, but older candidates keep their old `parsed_json` until a
    reparse rebuilds them. Costs apply (one parse-model call per resume +
    one embed-model call per candidate). The sticky-edit invariant still
    holds: any field a recruiter manually overrode stays put.
    """
    total = db.scalar(select(func.count()).select_from(Resume)) or 0
    if not confirm:
        return {
            "would_enqueue": int(total),
            "warning": (
                f"Will reparse {int(total)} resumes. Each runs the configured "
                f"parse model once and chains a re-embed. Pass "
                f"?confirm=true to proceed."
            ),
        }

    from app.workers.tasks.parse_resume import parse_resume

    resume_ids = list(db.scalars(select(Resume.id)).all())
    db.execute(
        Resume.__table__.update().values(parse_status="pending", parse_error=None)
    )
    audit_record(
        db, actor_id=admin.id, action="resumes.reparse_all", entity="system",
        payload={"enqueued": len(resume_ids)},
    )
    db.commit()

    for rid in resume_ids:
        parse_resume.delay(rid)

    return {"reparsed": True, "enqueued": len(resume_ids)}


# ----- audit log viewer (M6) --------------------------------------------


@router.get("/audit-log")
def list_audit(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    entity: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    stmt = select(AuditLog).order_by(AuditLog.at.desc())
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.offset(offset).limit(min(limit, 500))
    rows = list(db.scalars(stmt).all())

    # Hydrate actor names so the UI doesn't need a second round-trip.
    actor_ids = {r.actor_id for r in rows if r.actor_id is not None}
    actors: dict[int, str] = {}
    if actor_ids:
        for u in db.scalars(select(User).where(User.id.in_(actor_ids))).all():
            actors[u.id] = u.name

    return [
        {
            "id": r.id,
            "actor_id": r.actor_id,
            "actor_name": actors.get(r.actor_id) if r.actor_id else None,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "payload": r.payload,
            "at": r.at.isoformat(),
        }
        for r in rows
    ]


# ----- metrics (M6) -----------------------------------------------------


def _redis_queue_depth() -> int | None:
    """Best-effort: count tasks pending in Celery's default queue."""
    try:
        import redis

        s = get_settings()
        client = redis.Redis.from_url(s.redis_url, socket_timeout=2)
        return int(client.llen("celery"))
    except Exception:  # noqa: BLE001
        return None


@router.get("/metrics")
def metrics(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    s = get_settings()

    candidates_active = db.scalar(
        select(func.count()).select_from(Candidate).where(Candidate.deleted_at.is_(None))
    ) or 0
    candidates_deleted = db.scalar(
        select(func.count()).select_from(Candidate).where(Candidate.deleted_at.is_not(None))
    ) or 0
    clients_total = db.scalar(select(func.count()).select_from(Client)) or 0

    jobs_by_status_rows = db.execute(
        select(Job.status, func.count()).group_by(Job.status)
    ).all()
    jobs_by_status: dict[str, int] = {row[0]: row[1] for row in jobs_by_status_rows}

    resumes_by_status_rows = db.execute(
        select(Resume.parse_status, func.count()).group_by(Resume.parse_status)
    ).all()
    resumes_by_status: dict[str, int] = {row[0]: row[1] for row in resumes_by_status_rows}

    embedded = db.scalar(
        select(func.count()).select_from(CandidateEmbedding)
    ) or 0

    users_total = db.scalar(select(func.count()).select_from(User)) or 0
    users_active = db.scalar(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    ) or 0

    # Recent failures: parse_status == failed in the last 100 resumes
    recent_failed = db.scalar(
        select(func.count()).select_from(Resume).where(Resume.parse_status == "failed")
    ) or 0

    payload: dict[str, Any] = {
        "candidates": {
            "active": candidates_active,
            "soft_deleted": candidates_deleted,
            "embedded": embedded,
            "embedding_coverage": (
                round(embedded / candidates_active, 3) if candidates_active else 0.0
            ),
        },
        "clients": {"total": clients_total},
        "jobs": {
            "open": jobs_by_status.get("open", 0),
            "on_hold": jobs_by_status.get("on-hold", 0),
            "closed": jobs_by_status.get("closed", 0),
        },
        "resumes": {
            "pending": resumes_by_status.get("pending", 0),
            "parsing": resumes_by_status.get("parsing", 0),
            "done": resumes_by_status.get("done", 0),
            "failed": recent_failed,
        },
        "users": {"total": users_total, "active": users_active},
        "queue": {"celery_pending": _redis_queue_depth()},
        "models": {
            "parse": s.llm_parse_model,
            "embed": s.llm_embed_model,
            "embed_dim": s.llm_embed_dim,
            "qa": s.llm_qa_model,
        },
    }
    return payload
