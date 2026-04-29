from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decode_token
from app.models.user import User


def current_user(
    db: Annotated[Session, Depends(get_db)],
    session_cookie: Annotated[str | None, Cookie(alias=get_settings().cookie_name)] = None,
) -> User:
    if not session_cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(session_cookie)
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from e

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    # Client-role users with null client_id are effectively orphaned (their
    # tagged client was deleted). Lock them out — they have no scope to
    # operate within. An admin re-tagging or deactivating them is the fix.
    if user.role == "client" and user.client_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Client account is not tagged to a client; contact an admin.",
        )
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def require_admin_or_recruiter(
    user: Annotated[User, Depends(current_user)],
) -> User:
    """Blocks client-role users from endpoints that aren't scope-safe — e.g.
    job creation, candidate soft-delete, primary-resume changes. The default
    `current_user` lets clients through; this is the explicit gate."""
    if user.role not in ("admin", "recruiter"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin or recruiter only")
    return user
