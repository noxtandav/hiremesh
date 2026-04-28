from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.candidates import CandidateOut


class SearchRequest(BaseModel):
    q: str | None = Field(default=None, max_length=500)
    location: str | None = None
    skills: list[str] = []
    exp_min: Decimal | None = Field(default=None, ge=0)
    exp_max: Decimal | None = Field(default=None, ge=0)
    stage_name: str | None = None  # match candidates currently at this stage on any job
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class SearchHit(BaseModel):
    candidate: CandidateOut
    score: float | None = None  # null when no semantic query was supplied
