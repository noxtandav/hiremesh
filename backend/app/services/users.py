from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User


def create_user(
    db: Session,
    *,
    email: str,
    name: str,
    password: str,
    role: str,
    client_id: int | None = None,
) -> User:
    user = User(
        email=email.lower(),
        name=name,
        password_hash=hash_password(password),
        role=role,
        must_change_password=True,
        is_active=True,
        client_id=client_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))
