from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.user import User


def bootstrap_admin_if_needed(db: Session) -> User | None:
    """Create the first admin from BOOTSTRAP_ADMIN_* env vars if no users exist.

    Idempotent: a no-op once any user is in the table.
    """
    settings = get_settings()
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return None

    existing = db.scalar(select(User).limit(1))
    if existing is not None:
        return None

    admin = User(
        email=settings.bootstrap_admin_email.lower(),
        name=settings.bootstrap_admin_name,
        password_hash=hash_password(settings.bootstrap_admin_password),
        role="admin",
        must_change_password=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def create_user(
    db: Session, *, email: str, name: str, password: str, role: str
) -> User:
    user = User(
        email=email.lower(),
        name=name,
        password_hash=hash_password(password),
        role=role,
        must_change_password=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))
