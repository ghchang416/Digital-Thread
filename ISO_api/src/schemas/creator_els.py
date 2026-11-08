"""ELS candidate contracts. Not accepted as active CreatorDraft until G2/G3 gates pass."""
from typing import Annotated, Literal, Union
import unicodedata

from pydantic import Field, StrictBool, field_validator, model_validator

from src.schemas.creator import CreatorDraft, FieldValue, Identifier, Scalar, StrictModel
from src.schemas.creator_manual import ToolInput

Hash = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
SourceKey = Annotated[str, Field(strict=True, min_length=1, max_length=255, pattern=r".*\S.*")]
Reason = Annotated[str, Field(strict=True, min_length=1, max_length=1000, pattern=r".*\S.*")]
Table = Literal["Part_Info", "Operation_Info", "Operation_Machining", "Machine_Milling",
                "Tool_Milling", "Part_File", "Machine_File", "Tool_File"]


def unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


class ElsSourceRow(StrictModel):
    rowId: Identifier
    table: Table
    # Decimal values cross JSON as strings; source types remain explicit in the schema snapshot.
    values: dict[str, Scalar | None] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def bounded_cells(self):
        if any(not key or len(key) > 255 or key in {"__proto__", "constructor", "prototype"}
               or (isinstance(value, str) and len(value) > 4096)
               for key, value in self.values.items()):
            raise ValueError("Source cell exceeds snapshot limits")
        if any(type(value) is int and abs(value) > 9007199254740991 for value in self.values.values()):
            raise ValueError("Large source integers must be encoded as exact strings")
        return self


class ElsExcludedRow(StrictModel):
    rowId: Identifier
    reason: Reason


class ElsSelection(StrictModel):
    partNo: SourceKey
    partRevision: SourceKey
    opNo: SourceKey
    programNo: SourceKey
    programRevision: SourceKey
    orderedRowIds: list[Identifier] = Field(min_length=1, max_length=300)
    excludedRows: list[ElsExcludedRow] = Field(default_factory=list, max_length=1000)
    orderReason: Reason | None = None

    @model_validator(mode="after")
    def rows_are_distinct(self):
        unique(self.orderedRowIds + [row.rowId for row in self.excludedRows], "selected/excluded row")
        return self


class ElsValueChoice(StrictModel):
    rowId: Identifier
    ruleId: SourceKey
    column: SourceKey
    reason: Reason


class ElsIdentityChoice(StrictModel):
    rowId: Identifier
    configurationId: Identifier
    reason: Reason


class ElsToolValues(StrictModel):
    toolTag: Annotated[str, Field(strict=True, pattern=r"^T(?:0|[1-9][0-9]{0,5})$")]
    values: dict[str, ToolInput] = Field(min_length=1, max_length=30)
    reason: Reason


class ElsFileChoice(StrictModel):
    rowId: Identifier
    purpose: Literal["NC", "STEP", "OTHER"]
    reason: Reason


class ElsDecisions(StrictModel):
    templateId: Literal["freeform-milling-v1"] = "freeform-milling-v1"
    templateReason: Reason
    millingConfirmed: StrictBool
    valueChoices: list[ElsValueChoice] = Field(default_factory=list, max_length=1200)
    identityChoices: list[ElsIdentityChoice] = Field(default_factory=list, max_length=300)
    toolValues: list[ElsToolValues] = Field(default_factory=list, max_length=300)
    fileChoices: list[ElsFileChoice] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def distinct_choices(self):
        if not self.millingConfirmed:
            raise ValueError("ELS_MILLING_CONFIRMATION_REQUIRED")
        unique([(v.rowId, v.ruleId) for v in self.valueChoices], "value selection")
        unique([v.rowId for v in self.identityChoices], "identity selection")
        unique([v.toolTag for v in self.toolValues], "tool specification")
        unique([v.rowId for v in self.fileChoices], "file selection")
        return self


class ElsImport(StrictModel):
    importEntryId: Identifier
    sourceSha256: Hash
    sourceName: SourceKey
    readerVersion: SourceKey
    sourceSchemaHash: Hash
    profileHash: Hash
    selection: ElsSelection
    sourceRows: list[ElsSourceRow] = Field(min_length=1, max_length=1000)
    decisions: ElsDecisions | None = None

    @model_validator(mode="after")
    def selection_exists(self):
        unique([row.rowId for row in self.sourceRows], "source row")
        machining = {row.rowId for row in self.sourceRows if row.table == "Operation_Machining"}
        if not set(self.selection.orderedRowIds + [r.rowId for r in self.selection.excludedRows]) <= machining:
            raise ValueError("Selection must reference machining source rows")
        selected = set(self.selection.orderedRowIds + [r.rowId for r in self.selection.excludedRows])
        expected = dict(zip(("part_no", "part_rev", "op_no", "pgmno", "revno"),
                            (self.selection.partNo, self.selection.partRevision, self.selection.opNo,
                             self.selection.programNo, self.selection.programRevision)))
        for row in self.sourceRows:
            if row.rowId not in selected:
                continue
            values = {unicodedata.normalize("NFC", key).casefold(): value for key, value in row.values.items()}
            if len(values) != len(row.values) or any(values.get(key) != value for key, value in expected.items()):
                raise ValueError("Source row belongs to a different PART/revision/OP/program")
        return self


class ElsCellRef(StrictModel):
    rowId: Identifier
    column: SourceKey


class ElsOrigin(StrictModel):
    importEntryId: Identifier
    nodeId: Identifier
    fieldName: Identifier
    kind: Literal["source", "derived", "generated", "default", "placeholder", "manual"]
    sources: list[ElsCellRef] = Field(default_factory=list, max_length=16)
    appliedValue: FieldValue
    rule: SourceKey
    reason: Reason
    sourceUnit: SourceKey | None = None
    targetUnit: SourceKey | None = None

    @model_validator(mode="after")
    def source_evidence(self):
        if self.kind in {"source", "derived"} and not self.sources:
            raise ValueError("Mapped values require source cells")
        return self


class ElsSourceStep(StrictModel):
    kind: Literal["els"]
    stepNodeId: Identifier
    sourceRowId: Identifier


class ElsManualStep(StrictModel):
    kind: Literal["manual"]
    stepNodeId: Identifier
    reason: Reason


class ElsWorkplan(StrictModel):
    workplanNodeId: Identifier
    importEntryId: Identifier
    steps: list[Annotated[Union[ElsSourceStep, ElsManualStep], Field(discriminator="kind")]] = Field(min_length=1, max_length=300)


class ElsToolLink(StrictModel):
    workplanNodeId: Identifier
    stepNodeId: Identifier
    assetNodeId: Identifier
    toolTag: Annotated[str, Field(strict=True, pattern=r"^T[0-9]{1,6}$")]
    sourceToolNo: SourceKey | None = None


class ElsReview(StrictModel):
    workplanNodeId: Identifier
    snapshotHash: Hash
    profileHash: Hash
    acknowledged: Literal[True]


class ElsFileLink(StrictModel):
    mode: Literal["metadata-only"] = "metadata-only"
    assetNodeId: Identifier
    projectAssetNodeId: Identifier
    workplanNodeId: Identifier | None = None
    importEntryId: Identifier
    sourceRowId: Identifier
    sourcePath: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]
    purpose: Literal["NC", "STEP", "OTHER"]


class ElsMetadata(StrictModel):
    elsImports: list[ElsImport] = Field(default_factory=list, max_length=1000)
    elsOrigins: list[ElsOrigin] = Field(default_factory=list, max_length=20000)
    elsWorkplans: list[ElsWorkplan] = Field(default_factory=list, max_length=1000)
    elsToolLinks: list[ElsToolLink] = Field(default_factory=list, max_length=1000)
    elsReviews: list[ElsReview] = Field(default_factory=list, max_length=1000)
    elsFileLinks: list[ElsFileLink] = Field(default_factory=list, max_length=1000)


class ElsPrepareRequest(StrictModel):
    requestId: Identifier
    importId: Identifier
    baseDraftId: Identifier
    baseRevision: Annotated[int, Field(strict=True, ge=0)]
    expectedSequence: Annotated[int, Field(strict=True, ge=0)]
    mode: Literal["replace-project", "append-tools"]
    profileHash: Hash
    selection: ElsSelection
    includePlaceholders: StrictBool = False


class ElsCandidate(StrictModel):
    """Server-internal staged result; never pass its draft alone to active workspace APIs."""
    request: ElsPrepareRequest
    draft: CreatorDraft
    metadata: ElsMetadata
    requiredCapabilities: list[Literal["els-import-v1"]] = Field(default_factory=lambda: ["els-import-v1"], min_length=1, max_length=1)
    recoveryFormatVersion: Literal[2] = 2
    purpose: Literal["authoring-review-only"] = "authoring-review-only"
    machineReady: Literal[False] = False
    finalizable: Literal[False] = False
    persisted: Literal[False] = False

    @field_validator("machineReady", "finalizable", "persisted", mode="before")
    @classmethod
    def real_boolean(cls, value):
        if type(value) is not bool:
            raise ValueError("Review flags must be booleans")
        return value

    @model_validator(mode="after")
    def application_identity(self):
        if self.request.mode == "append-tools":
            if self.draft.draftId != self.request.baseDraftId or self.draft.revision != self.request.baseRevision + 1:
                raise ValueError("Append must preserve draft identity and increment revision once")
        elif self.draft.draftId == self.request.baseDraftId or self.draft.revision != 0:
            raise ValueError("Replacement requires a new draft identity at revision zero")
        return self


class ElsBuildRequest(StrictModel):
    request: ElsPrepareRequest
    baseDraft: CreatorDraft
    operationKey: Identifier
    programKey: Identifier
    projectName: Annotated[str, Field(strict=True, min_length=1, max_length=200, pattern=r".*\S.*")]
    globalAssetBaseUri: Annotated[str, Field(strict=True, min_length=1, max_length=1000)]
    decisions: ElsDecisions
    includeMachine: StrictBool = True
    includeMaterial: StrictBool = True


class ElsConfirmRequest(StrictModel):
    candidate: ElsCandidate
    workplanNodeIds: list[Identifier] = Field(min_length=1, max_length=1000)
    acknowledged: StrictBool


class ElsReviewRequest(StrictModel):
    candidate: ElsCandidate
    targetAssetNodeIds: list[Identifier] = Field(min_length=1, max_length=10)


class ElsCompleteRequest(StrictModel):
    candidate: ElsCandidate
    workplanNodeId: Identifier
    includePlaceholders: StrictBool = False
    synchronizeTools: StrictBool = False
