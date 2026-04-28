"""m4 candidate_embeddings pgvector

Enables the pgvector extension and adds the candidate_embeddings table
with an ivfflat index for cosine distance.

Revision ID: aa01c8e2f4d6
Revises: 75afa9bfaebf
Create Date: 2026-04-28 12:30:00.000000+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "aa01c8e2f4d6"
down_revision: str | None = "75afa9bfaebf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if is_pg:
        # Native pgvector column.
        op.execute(
            """
            CREATE TABLE candidate_embeddings (
                id SERIAL PRIMARY KEY,
                candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                source VARCHAR(32) NOT NULL DEFAULT 'combined',
                content TEXT NOT NULL,
                vector vector(1536) NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_candidate_embedding_source "
            "ON candidate_embeddings (candidate_id, source)"
        )
        op.execute(
            "CREATE INDEX ix_candidate_embeddings_candidate_id "
            "ON candidate_embeddings (candidate_id)"
        )
        # Ivfflat index for fast cosine ANN. lists=100 is a sane default for
        # the thousands-of-rows range; tune higher when the pool grows.
        op.execute(
            "CREATE INDEX ix_candidate_embeddings_vector "
            "ON candidate_embeddings USING ivfflat (vector vector_cosine_ops) "
            "WITH (lists = 100)"
        )
    else:
        # SQLite (tests only): JSON column for the vector — no ANN, but the
        # schema parses and the fallback search path ranks in Python.
        op.create_table(
            "candidate_embeddings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("candidate_id", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="combined"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("vector", sa.JSON(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "candidate_id", "source", name="uq_candidate_embedding_source"
            ),
        )
        op.create_index(
            "ix_candidate_embeddings_candidate_id",
            "candidate_embeddings",
            ["candidate_id"],
        )


def downgrade() -> None:
    op.drop_table("candidate_embeddings")
    # Leave the pgvector extension installed; dropping it would affect
    # anything else using it. Re-running the upgrade is idempotent.
