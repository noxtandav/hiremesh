from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.models.user import User
from app.schemas.candidates import CandidateOut
from app.schemas.search import SearchHit, SearchRequest
from app.services.search import search as run_search

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/candidates", response_model=list[SearchHit])
def search_candidates(
    body: SearchRequest,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    rows = run_search(db, body)
    return [
        SearchHit(candidate=CandidateOut.model_validate(c), score=score)
        for c, score in rows
    ]
