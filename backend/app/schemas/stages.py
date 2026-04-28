from pydantic import BaseModel, Field


class StageOut(BaseModel):
    id: int
    name: str
    position: int

    model_config = {"from_attributes": True}


class StageInput(BaseModel):
    """One stage as supplied by the client. id is optional — present when
    updating an existing stage, omitted to create a new one."""

    id: int | None = None
    name: str = Field(min_length=1, max_length=100)


class TemplateUpdate(BaseModel):
    """The full ordered list of stages. Anything not in the list is deleted.
    Order is implicit from list position."""

    stages: list[StageInput]
