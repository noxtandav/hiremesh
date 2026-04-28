from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import (
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserOut,
)
from app.services.audit import record as audit_record
from app.services.users import create_user, get_by_email

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return list(db.scalars(select(User).order_by(User.created_at.desc())).all())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create(
    body: CreateUserRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if get_by_email(db, body.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
    user = create_user(
        db,
        email=body.email,
        name=body.name,
        password=body.password,
        role=body.role,
    )
    audit_record(
        db,
        actor_id=admin.id,
        action="user.create",
        entity="user",
        entity_id=user.id,
        payload={"email": user.email, "role": user.role},
    )
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UpdateUserRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Self-protection: an admin can't deactivate themselves or demote the
    # last remaining admin into a recruiter (would lock everyone out).
    if target.id == admin.id and body.is_active is False:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You can't deactivate yourself"
        )

    will_become_recruiter = (
        target.role == "admin" and body.role == "recruiter"
    )
    if will_become_recruiter:
        remaining_admins = db.scalar(
            select(User)
            .where(User.role == "admin", User.is_active.is_(True), User.id != target.id)
            .limit(1)
        )
        if remaining_admins is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Cannot demote the last active admin",
            )

    changes: dict = {}
    for field in ("name", "role", "is_active"):
        new = getattr(body, field)
        if new is not None and getattr(target, field) != new:
            changes[field] = new
            setattr(target, field, new)

    if changes:
        audit_record(
            db,
            actor_id=admin.id,
            action="user.update",
            entity="user",
            entity_id=target.id,
            payload=changes,
        )

    db.commit()
    db.refresh(target)
    return target


@router.post(
    "/{user_id}/reset-password",
    response_model=UserOut,
)
def reset_password(
    user_id: int,
    body: ResetPasswordRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    target.password_hash = hash_password(body.new_password)
    target.must_change_password = True
    audit_record(
        db,
        actor_id=admin.id,
        action="user.reset_password",
        entity="user",
        entity_id=target.id,
    )
    db.commit()
    db.refresh(target)
    return target
