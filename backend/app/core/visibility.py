"""Row-level visibility helpers for the client role.

Returns a SQL subquery of ids the user can see, or None when no scoping
applies (admin / recruiter). Endpoints AND this onto their WHERE clauses.

Two scopes:
- jobs: filtered to the user's tagged client.
- candidates: filtered to those linked to the user's tagged client's jobs
  via candidate_jobs.

We use explicit subquery filtering rather than SQLAlchemy event hooks or a
"row level security" abstraction. Permission failures should be obvious
when reading the endpoint code; magic that hides them is worse.
"""

from __future__ import annotations

from sqlalchemy import Select, select

from app.models.job import Job
from app.models.pipeline import CandidateJob
from app.models.user import User


def is_client_role(user: User) -> bool:
    return user.role == "client"


def job_ids_visible_to(user: User) -> Select | None:
    """Subquery of job ids visible to the user, or None for admin/recruiter."""
    if not is_client_role(user) or user.client_id is None:
        return None
    return select(Job.id).where(Job.client_id == user.client_id)


def candidate_ids_visible_to(user: User) -> Select | None:
    """Subquery of candidate ids visible to the user, or None for admin/recruiter.

    Clients see candidates linked to any job of their tagged client.
    """
    if not is_client_role(user) or user.client_id is None:
        return None
    return (
        select(CandidateJob.candidate_id)
        .join(Job, Job.id == CandidateJob.job_id)
        .where(Job.client_id == user.client_id)
    )
