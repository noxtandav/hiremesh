from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.models.candidate import Candidate
from app.models.user import User
from app.schemas.candidates import CandidateCreate, CandidateOut, CandidateUpdate
from app.services.audit import record as audit_record
from app.services.candidates import apply_manual_edit

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _get_active_or_404(db: Session, candidate_id: int) -> Candidate:
    obj = db.get(Candidate, candidate_id)
    if obj is None or obj.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    return obj


@router.get("", response_model=list[CandidateOut])
def list_candidates(
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    stmt = select(Candidate).order_by(Candidate.created_at.desc())
    if not include_deleted:
        stmt = stmt.where(Candidate.deleted_at.is_(None))
    stmt = stmt.offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(
    body: CandidateCreate,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = Candidate(**body.model_dump())
    db.add(obj)
    db.flush()
    audit_record(
        db, actor_id=user.id, action="candidate.create", entity="candidate",
        entity_id=obj.id, payload={"full_name": obj.full_name},
    )
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_candidate(
    candidate_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return _get_active_or_404(db, candidate_id)


@router.patch("/{candidate_id}", response_model=CandidateOut)
def update_candidate(
    candidate_id: int,
    body: CandidateUpdate,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = _get_active_or_404(db, candidate_id)
    apply_manual_edit(db, obj, body.model_dump(exclude_unset=True), set_by=user.id)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_candidate(
    candidate_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = _get_active_or_404(db, candidate_id)
    obj.deleted_at = datetime.now(UTC)
    audit_record(
        db, actor_id=user.id, action="candidate.soft_delete", entity="candidate",
        entity_id=candidate_id, payload={"full_name": obj.full_name},
    )
    db.commit()


@router.get("/{candidate_id}/duplicates", response_model=list[CandidateOut])
def list_duplicates(
    candidate_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Candidates that look like the same person — same email (case-insensitive)
    or same phone — excluding self and soft-deleted rows.

    The bulk-import path can't run this at upload time (parse is async, so
    email/phone aren't known yet). This endpoint is meant to be called from
    the candidate detail page so the banner appears as soon as parsing fills
    those fields in.
    """
    candidate = _get_active_or_404(db, candidate_id)

    conditions = []
    if candidate.email:
        conditions.append(func.lower(Candidate.email) == candidate.email.lower())
    if candidate.phone:
        conditions.append(Candidate.phone == candidate.phone)
    if not conditions:
        return []

    stmt = (
        select(Candidate)
        .where(
            Candidate.id != candidate.id,
            Candidate.deleted_at.is_(None),
            or_(*conditions),
        )
        .order_by(Candidate.created_at.asc())
    )
    return list(db.scalars(stmt).all())


@router.post("/{candidate_id}/restore", response_model=CandidateOut)
def restore_candidate(
    candidate_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    obj = db.get(Candidate, candidate_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    if obj.deleted_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Candidate is not deleted")
    obj.deleted_at = None
    audit_record(
        db, actor_id=user.id, action="candidate.restore", entity="candidate",
        entity_id=candidate_id,
    )
    db.commit()
    db.refresh(obj)
    return obj
