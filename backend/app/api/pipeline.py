from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.models.candidate import Candidate
from app.models.job import Job, JobStage
from app.models.pipeline import CandidateJob, StageTransition
from app.models.user import User
from app.schemas.candidates import CandidateOut
from app.schemas.pipeline import (
    BoardColumn,
    CandidateJobOut,
    CandidateJobWithCandidate,
    LastTransition,
    LinkRequest,
    MoveRequest,
    StageTransitionOut,
)
from app.schemas.stages import StageOut
from app.services.pipeline import (
    board_for_job,
    link_candidate_to_job,
    move_to_stage,
    unlink,
)

# Two routers share this file: pipeline writes scoped to a job, and reads
# scoped to a single candidate-job link.
jobs_pipeline = APIRouter(tags=["pipeline"])
links = APIRouter(prefix="/candidate-jobs", tags=["pipeline"])


def _link_or_404(db: Session, link_id: int) -> CandidateJob:
    obj = db.get(CandidateJob, link_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return obj


# ----- on-job endpoints --------------------------------------------------


@jobs_pipeline.get("/jobs/{job_id}/board", response_model=list[BoardColumn])
def get_board(
    job_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        _job, stages, rows = board_for_job(db, job_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    # Hydrate the most recent transition per candidate within this job so
    # the kanban can show "moved Xd ago by Y" without a per-card fetch.
    # Use max(id) as the tiebreaker rather than max(at) — id is monotonic
    # within an autoincrement column, so it's reliable even when two rows
    # share the same timestamp.
    latest_id_per_candidate = (
        select(
            StageTransition.candidate_id.label("cid"),
            func.max(StageTransition.id).label("max_id"),
        )
        .where(StageTransition.job_id == job_id)
        .group_by(StageTransition.candidate_id)
        .subquery()
    )
    last_rows = db.execute(
        select(StageTransition, User.name)
        .select_from(StageTransition)
        .join(
            latest_id_per_candidate,
            StageTransition.id == latest_id_per_candidate.c.max_id,
        )
        .outerjoin(User, User.id == StageTransition.by_user)
    ).all()
    last_by_candidate: dict[int, LastTransition] = {
        t.candidate_id: LastTransition(
            at=t.at,
            by_user_id=t.by_user,
            by_user_name=user_name,
            from_stage_id=t.from_stage_id,
            to_stage_id=t.to_stage_id,
        )
        for t, user_name in last_rows
    }

    by_stage: dict[int, list[CandidateJobWithCandidate]] = {s.id: [] for s in stages}
    for link, candidate in rows:
        by_stage[link.current_stage_id].append(
            CandidateJobWithCandidate(
                **CandidateJobOut.model_validate(link).model_dump(),
                candidate=CandidateOut.model_validate(candidate),
                last_transition=last_by_candidate.get(candidate.id),
            )
        )
    return [
        BoardColumn(stage=StageOut.model_validate(s), links=by_stage[s.id])
        for s in stages
    ]


@jobs_pipeline.post(
    "/jobs/{job_id}/candidates",
    response_model=CandidateJobOut,
    status_code=status.HTTP_201_CREATED,
)
def add_candidate_to_job(
    job_id: int,
    body: LinkRequest,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if db.get(Job, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    candidate = db.get(Candidate, body.candidate_id)
    if candidate is None or candidate.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")

    existing = db.scalar(
        select(CandidateJob).where(
            CandidateJob.job_id == job_id,
            CandidateJob.candidate_id == body.candidate_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Candidate is already linked to this job"
        )

    return link_candidate_to_job(
        db, candidate_id=body.candidate_id, job_id=job_id, by_user=user.id
    )


# ----- per-link endpoints ------------------------------------------------


@links.patch("/{link_id}", response_model=CandidateJobOut)
def move(
    link_id: int,
    body: MoveRequest,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    link = _link_or_404(db, link_id)
    stage = db.get(JobStage, body.stage_id)
    if stage is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stage not found")
    try:
        return move_to_stage(db, link=link, target_stage=stage, by_user=user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@links.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_route(
    link_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    link = _link_or_404(db, link_id)
    unlink(db, link=link, by_user=user.id)


@links.get("/{link_id}/transitions", response_model=list[StageTransitionOut])
def list_transitions(
    link_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    link = _link_or_404(db, link_id)
    return list(
        db.scalars(
            select(StageTransition)
            .where(
                StageTransition.candidate_id == link.candidate_id,
                StageTransition.job_id == link.job_id,
            )
            .order_by(StageTransition.at)
        ).all()
    )


@links.get(
    "/by-candidate-and-job",
    response_model=CandidateJobOut,
)
def get_link_by_candidate_and_job(
    candidate_id: int,
    job_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    link = db.scalar(
        select(CandidateJob).where(
            CandidateJob.candidate_id == candidate_id,
            CandidateJob.job_id == job_id,
        )
    )
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return link
