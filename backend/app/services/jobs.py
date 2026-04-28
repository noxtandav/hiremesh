from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job, JobStage
from app.models.stage_template import StageTemplate
from app.schemas.jobs import JobCreate
from app.services.stages import seed_default_template_if_needed


def _copy_template_into_job(db: Session, job_id: int) -> list[JobStage]:
    """Deep-copy current stage_templates rows into job_stages for this job.

    Falls back to seeding the template if it's empty (defense in depth — the
    lifespan event also seeds, but this guards against a partial install where
    a job is created before the seed has run).
    """
    template = list(
        db.scalars(select(StageTemplate).order_by(StageTemplate.position)).all()
    )
    if not template:
        seed_default_template_if_needed(db)
        template = list(
            db.scalars(select(StageTemplate).order_by(StageTemplate.position)).all()
        )

    rows = [
        JobStage(job_id=job_id, name=t.name, position=t.position) for t in template
    ]
    db.add_all(rows)
    db.flush()
    return rows


def list_stages_for_job(db: Session, job_id: int) -> list[JobStage]:
    return list(
        db.scalars(
            select(JobStage)
            .where(JobStage.job_id == job_id)
            .order_by(JobStage.position)
        ).all()
    )


def create_job_with_stages(db: Session, body: JobCreate, created_by: int) -> Job:
    """Create a job and copy the current template into job_stages atomically."""
    job = Job(
        client_id=body.client_id,
        title=body.title,
        jd_text=body.jd_text,
        location=body.location,
        exp_min=body.exp_min,
        exp_max=body.exp_max,
        ctc_min=body.ctc_min,
        ctc_max=body.ctc_max,
        status=body.status,
        created_by=created_by,
    )
    db.add(job)
    db.flush()  # populate job.id
    _copy_template_into_job(db, job.id)
    db.commit()
    db.refresh(job)
    return job
