from datetime import datetime

from pydantic import BaseModel, Field


class NoteOut(BaseModel):
    id: int
    candidate_id: int
    candidate_job_id: int | None = None
    author_id: int | None
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NoteCreate(BaseModel):
    body: str = Field(min_length=1)


class NoteUpdate(BaseModel):
    body: str = Field(min_length=1)
