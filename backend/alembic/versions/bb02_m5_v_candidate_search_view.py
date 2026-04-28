"""m5 v_candidate_search view

A read-only flattened view over candidates + their current pipeline placement.
The pool Q&A SQL path queries ONLY this view — never raw schema.

Revision ID: bb02d6f3a8e1
Revises: aa01c8e2f4d6
Create Date: 2026-04-28 13:30:00.000000+00:00
"""
from collections.abc import Sequence

from alembic import op


revision: str = "bb02d6f3a8e1"
down_revision: str | None = "aa01c8e2f4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Columns the LLM is allowed to filter / select. Update both this view AND the
# whitelist in app/services/qa_pool.py:ALLOWED_COLUMNS in lockstep — the
# whitelist is the safety boundary, the view is just the data shape.
VIEW_SQL = """
CREATE OR REPLACE VIEW v_candidate_search AS
SELECT
    c.id                  AS candidate_id,
    c.full_name           AS full_name,
    c.email               AS email,
    c.phone               AS phone,
    c.location            AS location,
    c.current_company     AS current_company,
    c.current_title       AS current_title,
    c.total_exp_years     AS total_exp_years,
    c.current_ctc         AS current_ctc,
    c.expected_ctc        AS expected_ctc,
    c.notice_period_days  AS notice_period_days,
    c.skills              AS skills,
    c.summary             AS summary,
    c.created_at          AS created_at,
    c.deleted_at          AS deleted_at,
    -- Most recent active link (one job's stage). NULL if not currently linked.
    (
        SELECT js.name
        FROM candidate_jobs cj
        JOIN job_stages js ON js.id = cj.current_stage_id
        WHERE cj.candidate_id = c.id
        ORDER BY cj.linked_at DESC
        LIMIT 1
    ) AS current_stage_name,
    (
        SELECT j.title
        FROM candidate_jobs cj
        JOIN jobs j ON j.id = cj.job_id
        WHERE cj.candidate_id = c.id
        ORDER BY cj.linked_at DESC
        LIMIT 1
    ) AS current_job_title,
    (
        SELECT count(*)
        FROM candidate_jobs cj
        WHERE cj.candidate_id = c.id
    ) AS active_link_count,
    (
        SELECT count(*)
        FROM resumes r
        WHERE r.candidate_id = c.id
    ) AS resume_count,
    (
        SELECT count(*)
        FROM notes n
        WHERE n.candidate_id = c.id
    ) AS note_count
FROM candidates c
WHERE c.deleted_at IS NULL;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite tests don't exercise the view-based pool Q&A path; skip.
        return
    op.execute(VIEW_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP VIEW IF EXISTS v_candidate_search")
