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


class CandidateJobWithCandidate(CandidateJobOut):
    candidate: CandidateOut


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
