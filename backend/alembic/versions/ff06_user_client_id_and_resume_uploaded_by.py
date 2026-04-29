"""user client_id + resume uploaded_by

Two related additions for the new client role:
- `users.client_id` — the client a client-role user is tagged to. NULL for
  admin/recruiter. SET NULL on client delete (the user record survives but
  the auth layer refuses client-role users whose client_id has gone null).
- `resumes.uploaded_by` — attribution for who uploaded each resume. SET
  NULL on user delete so audit data survives.

Revision ID: ff06a4b2c3d5
Revises: ee05f6c8d2a1
Create Date: 2026-04-29 18:00:00.000000+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "ff06a4b2c3d5"
down_revision: str | None = "ee05f6c8d2a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "client_id",
                sa.Integer(),
                sa.ForeignKey("clients.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
    with op.batch_alter_table("resumes") as batch:
        batch.add_column(
            sa.Column(
                "uploaded_by",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.drop_column("uploaded_by")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("client_id")
