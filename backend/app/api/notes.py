from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.core.visibility import (
    candidate_ids_visible_to,
    is_client_role,
    job_ids_visible_to,
)
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.note import Note
from app.models.pipeline import CandidateJob
from app.models.user import User
from app.schemas.notes import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(tags=["notes"])


def _candidate_or_404(db: Session, candidate_id: int) -> Candidate:
    obj = db.get(Candidate, candidate_id)
    if obj is None or obj.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    return obj


def _note_or_404(db: Session, note_id: int) -> Note:
    obj = db.get(Note, note_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    return obj


def _own_or_admin(user: User, note: Note) -> None:
    if user.role != "admin" and note.author_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can only edit or delete your own notes"
        )


def _check_candidate_visible(db: Session, user: User, candidate_id: int) -> None:
    visible = candidate_ids_visible_to(user)
    if visible is None:
        return
    if (
        db.scalar(
            select(Candidate.id).where(
                Candidate.id == candidate_id, Candidate.id.in_(visible)
            )
        )
        is None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")


def _check_link_visible(db: Session, user: User, link: CandidateJob) -> None:
    if is_client_role(user):
        job = db.get(Job, link.job_id)
        if job is None or job.client_id != user.client_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")


@router.get(
    "/candidates/{candidate_id}/notes",
    response_model=list[NoteOut],
    tags=["candidates"],
)
def list_notes(
    candidate_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _check_candidate_visible(db, user, candidate_id)
    _candidate_or_404(db, candidate_id)
    stmt = (
        select(Note)
        .where(Note.candidate_id == candidate_id)
        .order_by(Note.created_at.desc())
    )
    # Privacy: clients see only their own notes (so internal recruiter
    # commentary stays internal) plus link-scoped notes on their visible
    # links — those are the per-job notes they wrote anyway, but matching
    # by author already covers that.
    if is_client_role(user):
        stmt = stmt.where(Note.author_id == user.id)
    return list(db.scalars(stmt).all())


@router.post(
    "/candidates/{candidate_id}/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    tags=["candidates"],
)
def create_note(
    candidate_id: int,
    body: NoteCreate,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _check_candidate_visible(db, user, candidate_id)
    _candidate_or_404(db, candidate_id)
    note = Note(candidate_id=candidate_id, author_id=user.id, body=body.body)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: int,
    body: NoteUpdate,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    note = _note_or_404(db, note_id)
    _own_or_admin(user, note)
    note.body = body.body
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    note = _note_or_404(db, note_id)
    _own_or_admin(user, note)
    db.delete(note)
    db.commit()


def _link_or_404(db: Session, link_id: int) -> CandidateJob:
    obj = db.get(CandidateJob, link_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return obj


@router.get(
    "/candidate-jobs/{link_id}/notes",
    response_model=list[NoteOut],
    tags=["pipeline"],
)
def list_link_notes(
    link_id: int,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    link = _link_or_404(db, link_id)
    _check_link_visible(db, user, link)
    stmt = (
        select(Note)
        .where(Note.candidate_job_id == link.id)
        .order_by(Note.created_at.desc())
    )
    if is_client_role(user):
        stmt = stmt.where(Note.author_id == user.id)
    return list(db.scalars(stmt).all())


@router.post(
    "/candidate-jobs/{link_id}/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
def create_link_note(
    link_id: int,
    body: NoteCreate,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    link = _link_or_404(db, link_id)
    _check_link_visible(db, user, link)
    note = Note(
        candidate_id=link.candidate_id,
        candidate_job_id=link.id,
        author_id=user.id,
        body=body.body,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
