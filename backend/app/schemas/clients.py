from datetime import datetime

from pydantic import BaseModel, Field


class ClientOut(BaseModel):
    id: int
    name: str
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClientWithStats(ClientOut):
    """Returned by GET /clients (list). Stats are aggregated per client so
    the dashboard can render activity at a glance without fanning out
    one-request-per-client.

    `candidates_recent` uses a fixed 7-day window — long enough to span a
    work week but short enough to mean "current activity"."""

    jobs_open: int = 0
    jobs_total: int = 0
    candidates_total: int = 0
    candidates_recent: int = 0


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    notes: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str | None = None
