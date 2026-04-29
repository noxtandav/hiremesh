from datetime import datetime

from pydantic import BaseModel

from app.schemas.candidates import CandidateOut
from app.schemas.stages import StageOut


class CandidateJobOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    current_stage_id: int
    linked_at: datetime

    model_config = {"from_attributes": True}


class LastTransition(BaseModel):
    """The most recent stage_transitions row for a candidate-job link.

    Hydrated server-side on the board response so the kanban can show
    "moved Xd ago by Y" without a per-card round-trip. `by_user_name` is
    null when the actor was deleted (FK is SET NULL)."""

    at: datetime
    by_user_id: int | None = None
    by_user_name: str | None = None
    from_stage_id: int | None = None
    to_stage_id: int | None = None


class CandidateJobWithCandidate(CandidateJobOut):
    candidate: CandidateOut
    last_transition: LastTransition | None = None


class LinkRequest(BaseModel):
    candidate_id: int


class MoveRequest(BaseModel):
    stage_id: int


class BoardColumn(BaseModel):
    stage: StageOut
    links: list[CandidateJobWithCandidate]


class StageTransitionOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    from_stage_id: int | None
    to_stage_id: int | None
    by_user: int | None
    at: datetime

    model_config = {"from_attributes": True}
