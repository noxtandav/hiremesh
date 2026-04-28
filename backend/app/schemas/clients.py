from datetime import datetime

from pydantic import BaseModel, Field


class ClientOut(BaseModel):
    id: int
    name: str
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    notes: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str | None = None
