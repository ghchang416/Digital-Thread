"""Strict draft graph transport; no database models or persistence behavior."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

Scalar = Union[StrictBool, StrictInt, StrictFloat, StrictStr]
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class NodeRef(StrictModel):
    node: Identifier = Field(alias="$node")


class ScalarItem(StrictModel):
    itemId: Identifier
    value: Scalar


FieldValue = Union[Scalar, NodeRef, list[Union[ScalarItem, NodeRef]]]


class SchemaNode(StrictModel):
    nodeId: Identifier
    typeId: Identifier
    fields: dict[str, FieldValue] = Field(default_factory=dict, max_length=512)


class AssetDraft(StrictModel):
    assetNodeId: Identifier
    elementNodeId: Identifier
    role: Literal["project", "machine", "material", "tool", "file"]


class FileLink(StrictModel):
    assetNodeId: Identifier
    fileId: Identifier
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    purpose: Literal["NC", "STEP", "OTHER"]
    workplanNodeId: Identifier | None = None


class ToolLink(StrictModel):
    workplanNodeId: Identifier
    toolTag: str = Field(pattern=r"^T[0-9]+$")
    assetNodeId: Identifier
    stepNodeIds: list[Identifier] = Field(default_factory=list, max_length=300)


class ManualEvidenceAssignment(StrictModel):
    stepNodeId: Identifier
    assetNodeId: Identifier
    toolTag: str = Field(pattern=r"^T[0-9]{1,6}$")
    lineStart: int = Field(ge=1, le=100000, strict=True)
    lineEnd: int = Field(ge=1, le=100000, strict=True)


class NcManualEvidence(StrictModel):
    version: Literal[1] = 1
    mode: Literal["manual"] = "manual"
    encoding: Literal["utf-8", "cp949"]
    reason: StrictStr = Field(min_length=1, max_length=1000)
    assignments: list[ManualEvidenceAssignment] = Field(min_length=1, max_length=300)
    snapshotHash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profileHash: str = Field(pattern=r"^[a-f0-9]{64}$")
    analyzerSupported: StrictBool
    diagnostics: list[StrictStr] = Field(max_length=100000)


class NcReview(StrictModel):
    workplanNodeId: Identifier
    fileId: Identifier
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    stepNodeIds: list[Identifier] = Field(min_length=1, max_length=300)
    manual: NcManualEvidence | None = None


class ManualToolLink(StrictModel):
    workplanNodeId: Identifier
    stepNodeId: Identifier
    assetNodeId: Identifier


class ManualTool(StrictModel):
    assetNodeId: Identifier
    toolTypeId: Identifier
    legacyUnits: StrictBool = False


class CompletionEntry(StrictModel):
    nodeId: Identifier
    fieldName: Identifier
    value: FieldValue
    kind: Literal["generated", "default", "placeholder", "batch"]
    rule: str = Field(max_length=200)
    reason: str = Field(max_length=500)


class ReferenceLink(StrictModel):
    sourceNodeId: Identifier
    policyId: Identifier
    targetAssetNodeId: Identifier


class CreatorDraft(StrictModel):
    draftVersion: Literal[1] = 1
    schemaVersion: str = Field(default="v31", min_length=1, max_length=64)
    schemaHash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rulesVersion: str
    draftId: Identifier
    revision: int = Field(ge=0, strict=True)
    nodes: dict[str, SchemaNode] = Field(max_length=10000)
    assets: list[AssetDraft] = Field(max_length=1000)
    projectAssetNodeId: Identifier
    fileLinks: list[FileLink] = Field(default_factory=list, max_length=1000)
    toolLinks: list[ToolLink] = Field(default_factory=list, max_length=1000)
    ncReviews: list[NcReview] = Field(default_factory=list, max_length=1000)
    completionEntries: list[CompletionEntry] = Field(default_factory=list, max_length=20000)
    referenceLinks: list[ReferenceLink] = Field(default_factory=list, max_length=10000)
    referencePolicyHash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    manualTools: list[ManualTool] = Field(default_factory=list, max_length=1000)
    manualToolLinks: list[ManualToolLink] = Field(default_factory=list, max_length=1000)
    manualWorkplans: list[Identifier] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def consistent_keys(self):
        if any(key != node.nodeId for key, node in self.nodes.items()):
            raise ValueError("Node dictionary keys must match nodeId")
        if len({asset.assetNodeId for asset in self.assets}) != len(self.assets):
            raise ValueError("Duplicate asset roots")
        return self


class PartialReviewRequest(StrictModel):
    mode: Literal["partial"] = "partial"
    draft: CreatorDraft
    targetAssetNodeIds: list[Identifier] = Field(min_length=1, max_length=10)
