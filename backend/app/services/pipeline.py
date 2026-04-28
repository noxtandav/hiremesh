"""Pipeline mutations: link, move, unlink. Every mutation that changes the
current stage writes a `stage_transitions` row in the same transaction so the
audit log can never drift from reality.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.job import Job, JobStage
from app.models.pipeline import CandidateJob, StageTransition


def _first_stage_for_job(db: Session, job_id: int) -> JobStage:
    stage = db.scalar(
        select(JobStage)
        .where(JobStage.job_id == job_id)
        .order_by(JobStage.position)
        .limit(1)
    )
    if stage is None:
        raise ValueError(f"Job {job_id} has no stages")
    return stage


def link_candidate_to_job(
    db: Session, *, candidate_id: int, job_id: int, by_user: int
) -> CandidateJob:
    """Create a candidate_jobs row at stage 0 and log the initial transition.

    Caller is responsible for verifying candidate and job exist and for
    producing a 409 if the link already exists.
    """
    stage = _first_stage_for_job(db, job_id)
    link = CandidateJob(
        candidate_id=candidate_id, job_id=job_id, current_stage_id=stage.id
    )
    db.add(link)
    db.flush()
    db.add(
        StageTransition(
            candidate_id=candidate_id,
            job_id=job_id,
            from_stage_id=None,
            to_stage_id=stage.id,
            by_user=by_user,
        )
    )
    db.commit()
    db.refresh(link)
    return link


def move_to_stage(
    db: Session, *, link: CandidateJob, target_stage: JobStage, by_user: int
) -> CandidateJob:
    """Move the candidate to a new stage on the same job. Idempotent on no-op
    moves (returns the link unchanged, no audit row written)."""
    if target_stage.job_id != link.job_id:
        raise ValueError("stage does not belong to this job")
    if target_stage.id == link.current_stage_id:
        return link

    db.add(
        StageTransition(
            candidate_id=link.candidate_id,
            job_id=link.job_id,
            from_stage_id=link.current_stage_id,
            to_stage_id=target_stage.id,
            by_user=by_user,
        )
    )
    link.current_stage_id = target_stage.id
    db.commit()
    db.refresh(link)
    return link


def unlink(db: Session, *, link: CandidateJob, by_user: int) -> None:
    """Remove the candidate_jobs row but preserve the audit trail.

    We log a final transition with `to_stage_id=None` so the history clearly
    shows the candidate left the pipeline.
    """
    db.add(
        StageTransition(
            candidate_id=link.candidate_id,
            job_id=link.job_id,
            from_stage_id=link.current_stage_id,
            to_stage_id=None,
            by_user=by_user,
        )
    )
    db.delete(link)
    db.commit()


def board_for_job(
    db: Session, job_id: int
) -> tuple[Job, list[JobStage], list[tuple[CandidateJob, Candidate]]]:
    """Return everything the kanban needs in one round-trip.

    Soft-deleted candidates are excluded — their links remain in the DB but
    aren't displayed.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise LookupError(f"job {job_id} not found")

    stages = list(
        db.scalars(
            select(JobStage)
            .where(JobStage.job_id == job_id)
            .order_by(JobStage.position)
        ).all()
    )

    rows = list(
        db.execute(
            select(CandidateJob, Candidate)
            .join(Candidate, CandidateJob.candidate_id == Candidate.id)
            .where(
                CandidateJob.job_id == job_id,
                Candidate.deleted_at.is_(None),
            )
            .order_by(CandidateJob.linked_at)
        ).all()
    )
    return job, stages, [(r[0], r[1]) for r in rows]
