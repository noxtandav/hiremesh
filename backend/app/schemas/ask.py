from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Citation(BaseModel):
    type: Literal["profile", "resume", "note", "row"]
    id: int | None = None
    snippet: str


class AskAnswer(BaseModel):
    answer: str
    citations: list[Citation] = []


class PoolAskAnswer(AskAnswer):
    """Pool answer carries extra metadata about how it was routed."""

    route: Literal["structured", "semantic", "hybrid"]
    matched_count: int | None = None  # number of candidates that matched (semantic/hybrid)
    rows: list[dict] | None = None  # raw rows when structured returns aggregations
