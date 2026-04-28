from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.db import Base
from app.core.vector_type import VectorColumn

# Read once at import time. To change at runtime, set `LLM_EMBED_DIM` in env
# and restart api/worker; then hit `POST /admin/embeddings/reset` so the DB
# column is recreated with the new dim.
EMBEDDING_DIM = get_settings().llm_embed_dim


class CandidateEmbedding(Base):
    """One row per `(candidate_id, source)`. M4 stores a single combined
    document per candidate (`source='combined'`); future milestones may split
    into per-resume / per-notes rows for finer retrieval.
    """

    __tablename__ = "candidate_embeddings"
    __table_args__ = (
        UniqueConstraint("candidate_id", "source", name="uq_candidate_embedding_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="combined")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector: Mapped[list[float]] = mapped_column(
        VectorColumn(EMBEDDING_DIM), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
