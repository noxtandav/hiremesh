from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Note(Base):
    """Recruiter-authored note.

    Two scopes:
    - `candidate_job_id IS NULL` — global note about the candidate.
    - `candidate_job_id` set — note attached to a specific candidate–job link
      (introduced in M3 for pipeline-stage commentary).
    """

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
