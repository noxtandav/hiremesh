from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StageTemplate(Base):
    """System-wide pipeline template. Editable by admins.

    A new job copies these rows into job_stages at creation time. Edits to the
    template do not retroactively propagate to existing jobs.
    """

    __tablename__ = "stage_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
