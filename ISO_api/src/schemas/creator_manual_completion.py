from pydantic import Field
from src.schemas.creator import Identifier
from src.schemas.creator_completion import CompletionRequest


class ManualCompletionRequest(CompletionRequest):
    expectedRevision: int = Field(ge=0, strict=True)
    profileHash: str = Field(pattern=r"^[a-f0-9]{64}$")
    stepNodeIds: list[Identifier] | None = Field(default=None, min_length=1, max_length=300)
