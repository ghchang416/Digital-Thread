from typing import Literal
from pydantic import Field, StrictBool, StrictFloat, StrictInt
from src.schemas.creator import CreatorDraft, Identifier, StrictModel


class CompletionRequest(StrictModel):
    draft: CreatorDraft
    workplanNodeId: Identifier
    includePlaceholders: StrictBool = False
    overrides: dict[str, StrictBool | StrictFloat | StrictInt | str] = Field(default_factory=dict, max_length=32)
    mode: Literal["missing-only"] = "missing-only"
