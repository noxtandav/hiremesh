from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user, require_admin_or_recruiter
from app.models.candidate import Candidate
from app.models.client import Client
from app.models.job import Job
from app.models.pipeline import CandidateJob, StageTransition
from app.models.user import User
from app.schemas.jobs import (
    JobCreate,
    JobOut,
    JobUpdate,
    JobWithStages,
    JobWithStats,
)
from app.schemas.stages import StageOut
from app.services.audit import record as audit_record
from app.services.jobs import create_job_with_stages, list_stages_for_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

RECENT_DAYS = 7


def _get_or_404(db: Session, job_id: int) -> Job:
    obj = db.get(Job, job_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return obj


def _check_visible(user: User, job: Job) -> None:
    """Client-role users can only access jobs of their tagged client."""
    if user.role == "client" and job.client_id != user.client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")


@router.get("", response_model=list[JobWithStats])
def list_jobs(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_id: int | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Jobs with per-job activity stats for the client-detail dashboard.

    Uses two grouped subqueries (candidate side + transition side) joined
    back to jobs, instead of a single multi-join GROUP BY — that would
    cartesian-product the candidate_jobs and stage_transitions rows and
    inflate the COUNTs even with DISTINCT.
    """
    recent_threshold = datetime.now(UTC) - timedelta(days=RECENT_DAYS)

    cand_stats = (
        select(
            CandidateJob.job_id.label("jid"),
            func.count(distinct(CandidateJob.candidate_id)).label("c_total"),
            func.count(
                distinct(
                    case(
                        (CandidateJob.linked_at >= recent_threshold, CandidateJob.candidate_id),
                        else_=None,
                    )
                )
            ).label("c_recent"),
        )
        .select_from(CandidateJob)
        .join(
            Candidate,
            and_(
                Candidate.id == CandidateJob.candidate_id,
                Candidate.deleted_at.is_(None),
            ),
        )
        .group_by(CandidateJob.job_id)
        .subquery()
    )

    move_stats = (
        select(
            StageTransition.job_id.label("jid"),
            func.count(StageTransition.id).label("m_recent"),
        )
        .where(StageTransition.at >= recent_threshold)
        .group_by(StageTransition.job_id)
        .subquery()
    )

    stmt = (
        select(
            Job,
            cand_stats.c.c_total,
            cand_stats.c.c_recent,
            move_stats.c.m_recent,
        )
        .outerjoin(cand_stats, cand_stats.c.jid == Job.id)
        .outerjoin(move_stats, move_stats.c.jid == Job.id)
        .order_by(Job.created_at.desc())
    )
    if client_id is not None:
        stmt = stmt.where(Job.client_id == client_id)
    if status_filter is not None:
        stmt = stmt.where(Job.status == status_filter)
    if user.role == "client" and user.client_id is not None:
        stmt = stmt.where(Job.client_id == user.client_id)
    stmt = stmt.offset(offset).limit(limit)

    rows = db.execute(stmt).all()
    return [
        JobWithStats(
            **JobOut.model_validate(job).model_dump(),
            candidates_total=int(c_total or 0),
            candidates_recent=int(c_recent or 0),
            moves_recent=int(m_recent or 0),
        )
        for job, c_total, c_recent, m_recent in rows
    ]


@router.post("", response_model=JobWithStages, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobCreate,
    user: Annotated[User, Depends(require_admin_or_recruiter)],
    db: Annotated[Session, Depends(get_db)],
):
    if db.get(Client, body.client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    job = create_job_with_stages(db, body, created_by=user.id)
    stages = list_stages_for_job(db, job.id)
    audit_record(
        db, actor_id=user.id, action="job.create", entity="job", entity_id=job.id,
        payload={"title": job.title, "client_id": job.client_id},
    )
    db.commit()
    return JobWithStages(
        **JobOut.model_validate(job).model_dump(),
        stages=[StageOut.model_validate(s) for s in stages],
    )


@router.get("/{job_id}", response_model=JobWithStages)
def get_job(
    job_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    job = _get_or_404(db, job_id)
    _check_visible(user, job)
    stages = list_stages_for_job(db, job_id)
    return JobWithStages(
        **JobOut.model_validate(job).model_dump(),
        stages=[StageOut.model_validate(s) for s in stages],
    )


@router.patch("/{job_id}", response_model=JobOut)
def update_job(
    job_id: int,
    body: JobUpdate,
    _user: Annotated[User, Depends(require_admin_or_recruiter)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = _get_or_404(db, job_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int,
    user: Annotated[User, Depends(require_admin_or_recruiter)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = _get_or_404(db, job_id)
    title = obj.title
    db.delete(obj)
    audit_record(
        db, actor_id=user.id, action="job.delete", entity="job",
        entity_id=job_id, payload={"title": title},
    )
    db.commit()
