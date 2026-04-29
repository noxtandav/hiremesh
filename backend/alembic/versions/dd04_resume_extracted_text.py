"""resume extracted text

Adds resumes.extracted_text — the raw, post-extraction body of the resume.
We were storing only the LLM's structured `parsed_json`, which loses any
info that didn't make it into a structured field (project mentions,
work-history details, technologies named in prose). The extracted text is
what the per-candidate Q&A path needs to answer questions about anything
that appears in the resume.

Revision ID: dd04e5b9a3c2
Revises: cc03e9a4b2f7
Create Date: 2026-04-29 11:00:00.000000+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "dd04e5b9a3c2"
down_revision: str | None = "cc03e9a4b2f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column("extracted_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    # batch_alter_table so SQLite (used in unit tests) can drop the column.
    with op.batch_alter_table("resumes") as batch:
        batch.drop_column("extracted_text")
