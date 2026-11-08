import type { Draft, FieldValue, Scalar } from '../../shared/schema/types';

// Staged ELS transport, not active Draft/WorkspaceData. G2/G3 must validate before applying.
export const ELS_FIELDS = ['elsImports', 'elsOrigins', 'elsWorkplans', 'elsToolLinks', 'elsReviews', 'elsFileLinks'] as const;
export type ElsTable = 'Part_Info' | 'Operation_Info' | 'Operation_Machining' | 'Machine_Milling' | 'Tool_Milling' | 'Part_File' | 'Machine_File' | 'Tool_File';
export interface ElsSourceRow { rowId: string; table: ElsTable; values: Record<string, Scalar | null> }
export interface ElsSelection {
  partNo: string; partRevision: string; opNo: string; programNo: string; programRevision: string;
  orderedRowIds: string[]; excludedRows: { rowId: string; reason: string }[]; orderReason: string | null;
}
export interface ElsImport {
  importEntryId: string; sourceSha256: string; sourceName: string; readerVersion: string;
  sourceSchemaHash: string; profileHash: string; selection: ElsSelection; sourceRows: ElsSourceRow[];
  decisions?: ElsDecisions | null;
}
export interface ElsDecisions {
  templateId: 'freeform-milling-v1'; templateReason: string; millingConfirmed: true;
  valueChoices: { rowId: string; ruleId: string; column: string; reason: string }[];
  identityChoices: { rowId: string; configurationId: string; reason: string }[];
  toolValues: { toolTag: string; values: Record<string, { value: number; unit: 'mm' | 'in' | '1' | 'deg' }>; reason: string }[];
  fileChoices: { rowId: string; purpose: 'NC' | 'STEP' | 'OTHER'; reason: string }[];
}
export interface ElsOrigin {
  importEntryId: string; nodeId: string; fieldName: string;
  kind: 'source' | 'derived' | 'generated' | 'default' | 'placeholder' | 'manual';
  sources: { rowId: string; column: string }[]; appliedValue: FieldValue; rule: string; reason: string;
  sourceUnit: string | null; targetUnit: string | null;
}
export type ElsStep = { kind: 'els'; stepNodeId: string; sourceRowId: string } | { kind: 'manual'; stepNodeId: string; reason: string };
export interface ElsWorkplan { workplanNodeId: string; importEntryId: string; steps: ElsStep[] }
export interface ElsToolLink { workplanNodeId: string; stepNodeId: string; assetNodeId: string; toolTag: string; sourceToolNo: string | null }
export interface ElsReview { workplanNodeId: string; snapshotHash: string; profileHash: string; acknowledged: true }
export interface ElsFileLink {
  mode: 'metadata-only'; assetNodeId: string; projectAssetNodeId: string; workplanNodeId: string | null;
  importEntryId: string; sourceRowId: string; sourcePath: string; purpose: 'NC' | 'STEP' | 'OTHER';
}
export interface ElsMetadata {
  elsImports: ElsImport[]; elsOrigins: ElsOrigin[]; elsWorkplans: ElsWorkplan[];
  elsToolLinks: ElsToolLink[]; elsReviews: ElsReview[]; elsFileLinks: ElsFileLink[];
}
export interface ElsPrepareRequest {
  requestId: string; importId: string; baseDraftId: string; baseRevision: number; expectedSequence: number;
  mode: 'replace-project' | 'append-tools'; profileHash: string; selection: ElsSelection; includePlaceholders: boolean;
}
export interface ElsCandidate {
  request: ElsPrepareRequest; draft: Draft; metadata: ElsMetadata;
  requiredCapabilities: ['els-import-v1']; recoveryFormatVersion: 2;
  purpose: 'authoring-review-only'; machineReady: false; finalizable: false; persisted: false;
}

export function hasUnintegratedElsData(value: object): boolean {
  const object = value as Record<string, unknown>;
  return ELS_FIELDS.some(key => key in object && (!Array.isArray(object[key]) || (object[key] as unknown[]).length > 0));
}
