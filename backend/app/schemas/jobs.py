from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.stages import StageOut


class JobOut(BaseModel):
    id: int
    client_id: int
    title: str
    jd_text: str | None = None
    location: str | None = None
    exp_min: Decimal | None = None
    exp_max: Decimal | None = None
    ctc_min: Decimal | None = None
    ctc_max: Decimal | None = None
    status: Literal["open", "on-hold", "closed"]
    created_at: datetime

    model_config = {"from_attributes": True}


class JobWithStages(JobOut):
    stages: list[StageOut]


class _RangeMixin(BaseModel):
    @model_validator(mode="after")
    def _check_ranges(self):
        for lo, hi, label in [
            (self.exp_min, self.exp_max, "exp"),
            (self.ctc_min, self.ctc_max, "ctc"),
        ]:
            if lo is not None and hi is not None and lo > hi:
                raise ValueError(f"{label}_min must be <= {label}_max")
        return self


class JobCreate(_RangeMixin):
    client_id: int
    title: str = Field(min_length=1, max_length=255)
    jd_text: str | None = None
    location: str | None = Field(default=None, max_length=255)
    exp_min: Decimal | None = Field(default=None, ge=0)
    exp_max: Decimal | None = Field(default=None, ge=0)
    ctc_min: Decimal | None = Field(default=None, ge=0)
    ctc_max: Decimal | None = Field(default=None, ge=0)
    status: Literal["open", "on-hold", "closed"] = "open"


class JobUpdate(_RangeMixin):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    jd_text: str | None = None
    location: str | None = Field(default=None, max_length=255)
    exp_min: Decimal | None = Field(default=None, ge=0)
    exp_max: Decimal | None = Field(default=None, ge=0)
    ctc_min: Decimal | None = Field(default=None, ge=0)
    ctc_max: Decimal | None = Field(default=None, ge=0)
    status: Literal["open", "on-hold", "closed"] | None = None
