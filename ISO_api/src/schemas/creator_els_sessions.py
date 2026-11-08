"""Inspection-only HTTP contracts; no active draft migration or persistence."""
from typing import Any, Literal

from pydantic import Field

from .creator import StrictModel


class ElsTableSummary(StrictModel):
    name: str
    rowCount: int
    columnCount: int
    primaryKey: list[str]


class ElsImportStatus(StrictModel):
    importId: str
    requestId: str
    status: Literal["uploading", "queued", "reading", "ready", "failed"]
    expiresAt: str
    sourceName: str
    size: int
    errorCode: str | None = None
    sourceSha256: str | None = None
    format: str | None = None
    readerVersion: str | None = None
    operationCount: int | None = None
    diagnosticCount: int | None = None
    tables: list[ElsTableSummary] = Field(default_factory=list)
    persisted: Literal[False] = False


class ElsImportAccepted(ElsImportStatus):
    ownerToken: str


class ElsSourcePage(StrictModel):
    items: list[dict[str, Any]]
    total: int
    nextCursor: str | None


class ElsOperationDetail(StrictModel):
    operation: dict[str, Any]
    programs: ElsSourcePage
    issueCount: int
    issues: list[dict[str, Any]]
