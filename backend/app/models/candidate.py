from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Candidate(Base):
    """Talent pool entry. One row per person.

    Skills are stored as JSON for portability across Postgres + sqlite. On
    Postgres this is jsonb; on sqlite (used in tests) it's a TEXT column.
    """

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_exp_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    current_ctc: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_ctc: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
