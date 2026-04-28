from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.models.client import Client
from app.models.job import Job
from app.models.user import User
from app.schemas.jobs import JobCreate, JobOut, JobUpdate, JobWithStages
from app.schemas.stages import StageOut
from app.services.audit import record as audit_record
from app.services.jobs import create_job_with_stages, list_stages_for_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_or_404(db: Session, job_id: int) -> Job:
    obj = db.get(Job, job_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return obj


@router.get("", response_model=list[JobOut])
def list_jobs(
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_id: int | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    stmt = select(Job).order_by(Job.created_at.desc())
    if client_id is not None:
        stmt = stmt.where(Job.client_id == client_id)
    if status_filter is not None:
        stmt = stmt.where(Job.status == status_filter)
    stmt = stmt.offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("", response_model=JobWithStages, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobCreate,
    user: Annotated[User, Depends(current_user)],
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
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    job = _get_or_404(db, job_id)
    stages = list_stages_for_job(db, job_id)
    return JobWithStages(
        **JobOut.model_validate(job).model_dump(),
        stages=[StageOut.model_validate(s) for s in stages],
    )


@router.patch("/{job_id}", response_model=JobOut)
def update_job(
    job_id: int,
    body: JobUpdate,
    _user: Annotated[User, Depends(current_user)],
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
    user: Annotated[User, Depends(current_user)],
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
