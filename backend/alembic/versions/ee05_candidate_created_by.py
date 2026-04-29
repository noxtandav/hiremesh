"""candidate created_by

Adds candidates.created_by — the user who first added the candidate. M1
deliberately omitted this column to avoid back-filling NULLs in a future
migration; we're adding it now and accepting the NULLs (they only apply to
historical rows).

`SET NULL` on user delete: deactivating or removing a recruiter shouldn't
vacuum out their candidates.

Revision ID: ee05f6c8d2a1
Revises: dd04e5b9a3c2
Create Date: 2026-04-29 16:30:00.000000+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "ee05f6c8d2a1"
down_revision: str | None = "dd04e5b9a3c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite needs batch mode to add a column with a foreign-key constraint.
    with op.batch_alter_table("candidates") as batch:
        batch.add_column(
            sa.Column(
                "created_by",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("candidates") as batch:
        batch.drop_column("created_by")
