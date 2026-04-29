from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.core.visibility import candidate_ids_visible_to
from app.models.candidate import Candidate
from app.models.user import User
from app.schemas.ask import AskAnswer, AskRequest, PoolAskAnswer
from app.services.qa_candidate import answer_for_candidate
from app.services.qa_pool import answer_pool

router = APIRouter(prefix="/ask", tags=["ask"])


def _candidate_or_404(db: Session, candidate_id: int) -> Candidate:
    obj = db.get(Candidate, candidate_id)
    if obj is None or obj.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    return obj


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


@router.post("/candidate/{candidate_id}", response_model=AskAnswer)
def ask_candidate(
    candidate_id: int,
    body: AskRequest,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _check_candidate_visible(db, user, candidate_id)
    candidate = _candidate_or_404(db, candidate_id)
    return answer_for_candidate(db, candidate, body.question)


@router.post("/pool", response_model=PoolAskAnswer)
def ask_pool(
    body: AskRequest,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return answer_pool(db, body.question, visible_ids=candidate_ids_visible_to(user))
