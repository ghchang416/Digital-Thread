from typing import Literal
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr
from src.schemas.creator import CreatorDraft, Identifier, StrictModel


class ManualRequest(StrictModel):
    draft: CreatorDraft
    expectedRevision: int = Field(ge=0, strict=True)
    profileHash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ToolInput(StrictModel):
    value: StrictInt | StrictFloat
    unit: Literal["mm", "in", "1", "deg"]


class ManualToolRequest(ManualRequest):
    assetNodeId: Identifier | None = None
    name: StrictStr = Field(min_length=1, max_length=200)
    toolTypeId: Identifier
    values: dict[str, ToolInput] = Field(max_length=30)
    synchronize: StrictBool = False


class ManualStepRequest(ManualRequest):
    action: Literal["add", "assign", "unassign"]
    workplanNodeId: Identifier
    stepNodeId: Identifier | None = None
    assetNodeId: Identifier | None = None
    name: StrictStr = Field(default="", max_length=200)
    operationTypeId: Identifier | None = None
    synchronize: StrictBool = False
    adoptExisting: StrictBool = False


class ManualAssignment(StrictModel):
    stepNodeId: Identifier
    toolTag: str = Field(pattern=r"^[Tt][0-9]{1,6}$")
    lineStart: int = Field(ge=1, le=100000, strict=True)
    lineEnd: int = Field(ge=1, le=100000, strict=True)


class ManualNcRequest(ManualRequest):
    workplanNodeId: Identifier
    fileId: Identifier
    encoding: Literal["utf-8", "cp949"] = "utf-8"
    assignments: list[ManualAssignment] = Field(min_length=1, max_length=300)
    acknowledged: StrictBool
    reason: StrictStr = Field(min_length=1, max_length=1000)
