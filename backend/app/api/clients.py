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
from app.models.pipeline import CandidateJob
from app.models.user import User
from app.schemas.clients import ClientCreate, ClientOut, ClientUpdate, ClientWithStats
from app.services.audit import record as audit_record

router = APIRouter(prefix="/clients", tags=["clients"])

RECENT_DAYS = 7


def _get_or_404(db: Session, client_id: int) -> Client:
    obj = db.get(Client, client_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return obj


def _check_visible(user: User, client_id: int) -> None:
    """Client-role users can only access their own tagged client."""
    if user.role == "client" and user.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")


@router.get("", response_model=list[ClientWithStats])
def list_clients(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 100,
    offset: int = 0,
):
    """Clients with per-client activity stats for the dashboard.

    One grouped query joins clients → jobs → candidate_jobs → candidates so
    we don't fan out N+1. Soft-deleted candidates are excluded from the
    candidate counts; they're still visible at the per-job level if a
    recruiter wants to dig in.
    """
    recent_threshold = datetime.now(UTC) - timedelta(days=RECENT_DAYS)

    stmt = (
        select(
            Client.id,
            Client.name,
            Client.notes,
            Client.created_at,
            func.count(
                distinct(case((Job.status == "open", Job.id), else_=None))
            ).label("jobs_open"),
            func.count(distinct(Job.id)).label("jobs_total"),
            func.count(
                distinct(
                    case(
                        (Candidate.deleted_at.is_(None), CandidateJob.candidate_id),
                        else_=None,
                    )
                )
            ).label("candidates_total"),
            func.count(
                distinct(
                    case(
                        (
                            and_(
                                Candidate.deleted_at.is_(None),
                                CandidateJob.linked_at >= recent_threshold,
                            ),
                            CandidateJob.candidate_id,
                        ),
                        else_=None,
                    )
                )
            ).label("candidates_recent"),
        )
        .select_from(Client)
        .outerjoin(Job, Job.client_id == Client.id)
        .outerjoin(CandidateJob, CandidateJob.job_id == Job.id)
        .outerjoin(Candidate, Candidate.id == CandidateJob.candidate_id)
        .group_by(Client.id, Client.name, Client.notes, Client.created_at)
        .order_by(Client.name)
        .offset(offset)
        .limit(limit)
    )
    if user.role == "client" and user.client_id is not None:
        stmt = stmt.where(Client.id == user.client_id)

    rows = db.execute(stmt).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "notes": r.notes,
            "created_at": r.created_at,
            "jobs_open": int(r.jobs_open or 0),
            "jobs_total": int(r.jobs_total or 0),
            "candidates_total": int(r.candidates_total or 0),
            "candidates_recent": int(r.candidates_recent or 0),
        }
        for r in rows
    ]


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    body: ClientCreate,
    user: Annotated[User, Depends(require_admin_or_recruiter)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = Client(name=body.name, notes=body.notes)
    db.add(obj)
    db.flush()
    audit_record(
        db, actor_id=user.id, action="client.create", entity="client", entity_id=obj.id,
        payload={"name": obj.name},
    )
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _check_visible(user, client_id)
    return _get_or_404(db, client_id)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    body: ClientUpdate,
    _user: Annotated[User, Depends(require_admin_or_recruiter)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = _get_or_404(db, client_id)
    if body.name is not None:
        obj.name = body.name
    if body.notes is not None:
        obj.notes = body.notes
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    user: Annotated[User, Depends(require_admin_or_recruiter)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = _get_or_404(db, client_id)
    from app.models.job import Job  # local import; Job is added in M1.3

    has_jobs = db.scalar(select(Job.id).where(Job.client_id == client_id).limit(1))
    if has_jobs is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Client has jobs; remove or close them before deleting the client.",
        )
    name = obj.name
    db.delete(obj)
    audit_record(
        db, actor_id=user.id, action="client.delete", entity="client",
        entity_id=client_id, payload={"name": name},
    )
    db.commit()
