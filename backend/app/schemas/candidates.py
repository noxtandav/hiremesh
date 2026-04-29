from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class CandidateOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr | None = None
    phone: str | None = None
    location: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    total_exp_years: Decimal | None = None
    current_ctc: Decimal | None = None
    expected_ctc: Decimal | None = None
    notice_period_days: int | None = None
    skills: list[str] = []
    summary: str | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    created_by: int | None = None
    # Hydrated by the detail endpoint so the UI can render "Added by X"
    # without a second round-trip. Null on list endpoints (each row would
    # require a separate user lookup; the list view doesn't need it).
    created_by_name: str | None = None

    model_config = {"from_attributes": True}


class CandidateCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    current_company: str | None = Field(default=None, max_length=255)
    current_title: str | None = Field(default=None, max_length=255)
    total_exp_years: Decimal | None = Field(default=None, ge=0)
    current_ctc: Decimal | None = Field(default=None, ge=0)
    expected_ctc: Decimal | None = Field(default=None, ge=0)
    notice_period_days: int | None = Field(default=None, ge=0)
    skills: list[str] = []
    summary: str | None = None


class CandidateUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    current_company: str | None = Field(default=None, max_length=255)
    current_title: str | None = Field(default=None, max_length=255)
    total_exp_years: Decimal | None = Field(default=None, ge=0)
    current_ctc: Decimal | None = Field(default=None, ge=0)
    expected_ctc: Decimal | None = Field(default=None, ge=0)
    notice_period_days: int | None = Field(default=None, ge=0)
    skills: list[str] | None = None
    summary: str | None = None
