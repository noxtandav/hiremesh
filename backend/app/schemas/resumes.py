from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ResumeOut(BaseModel):
    id: int
    candidate_id: int
    filename: str
    mime: str
    is_primary: bool
    parse_status: Literal["pending", "parsing", "done", "failed"]
    parse_error: str | None = None
    parsed_json: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PresignedUrl(BaseModel):
    url: str
    expires_in: int
