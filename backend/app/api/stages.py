from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user, require_admin
from app.models.user import User
from app.schemas.stages import StageOut, TemplateUpdate
from app.services.stages import list_template, replace_template

router = APIRouter(prefix="/stages", tags=["stages"])


@router.get("/template", response_model=list[StageOut])
def get_template(
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return list_template(db)


@router.put("/template", response_model=list[StageOut])
def update_template(
    body: TemplateUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return replace_template(db, body.stages)
