from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.models.client import Client
from app.models.user import User
from app.schemas.clients import ClientCreate, ClientOut, ClientUpdate
from app.services.audit import record as audit_record

router = APIRouter(prefix="/clients", tags=["clients"])


def _get_or_404(db: Session, client_id: int) -> Client:
    obj = db.get(Client, client_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return obj


@router.get("", response_model=list[ClientOut])
def list_clients(
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 100,
    offset: int = 0,
):
    return list(
        db.scalars(
            select(Client).order_by(Client.name).offset(offset).limit(limit)
        ).all()
    )


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    body: ClientCreate,
    user: Annotated[User, Depends(current_user)],
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
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return _get_or_404(db, client_id)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    body: ClientUpdate,
    _user: Annotated[User, Depends(current_user)],
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
    user: Annotated[User, Depends(current_user)],
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
