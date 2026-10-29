from typing import Literal
from pydantic import Field
from src.schemas.creator import CreatorDraft, Identifier, StrictModel


class NcAnalyzeRequest(StrictModel):
    fileId: Identifier
    encoding: Literal["utf-8", "cp949"] = "utf-8"


class NcAssignment(StrictModel):
    stepNodeId: Identifier
    eventId: str = Field(min_length=1, max_length=128)


class NcToolsRequest(NcAnalyzeRequest):
    draft: CreatorDraft
    workplanNodeId: Identifier
    fileAssetNodeId: Identifier
    assignments: list[NcAssignment] = Field(min_length=1, max_length=300)
    resolutions: dict[str, dict[str, float]] = Field(default_factory=dict, max_length=300)
