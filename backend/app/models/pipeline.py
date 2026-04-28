from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CandidateJob(Base):
    """A candidate's link to a specific job, tracking which stage they're in.

    Permanent stage history lives in `stage_transitions`; this row only holds
    the *current* stage. Unlinking deletes this row but does NOT delete the
    transitions — the audit trail stays.
    """

    __tablename__ = "candidate_jobs"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_stage_id: Mapped[int] = mapped_column(
        ForeignKey("job_stages.id", ondelete="RESTRICT"), nullable=False
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StageTransition(Base):
    """Permanent audit row: candidate moved between two stages on a job.

    We *do not* FK back to candidate_jobs because we want this row to outlive
    an unlink. Instead we store candidate_id + job_id directly.

    `from_stage_id` is null for the initial placement when the candidate was
    first linked to the job.
    """

    __tablename__ = "stage_transitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_stages.id", ondelete="SET NULL"), nullable=True
    )
    to_stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_stages.id", ondelete="SET NULL"), nullable=True
    )
    by_user: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
