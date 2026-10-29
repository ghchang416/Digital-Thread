export interface Field {
  fieldName: string; label: string; declaredBy: string; xmlName: string;
  xmlKind: string; namespace: string | null; kind: 'object' | 'enum' | 'scalar';
  objectTypes: string[]; enumTypes: string[]; scalarTypes: string[];
  repeated: boolean; required: boolean; minOccurs: number; maxOccurs: number | null; managed: boolean;
  referencePolicyId?: string | null;
}
export interface SchemaType {
  typeId: string; label: string; xmlName: string; bases: string[]; descendants: string[];
  fields: Field[]; semanticStatus: string;
}
export interface Catalog {
  catalogVersion: number; schemaVersion: string; schemaHash: string; rulesVersion: string;
  referencePolicies?: ReferencePolicy[]; referencePolicyHash?: string;
  types: Record<string, SchemaType>; enums: Record<string, string[]>; rootTypes: string[];
  capabilities: { partialPreview: boolean; finalReview: boolean; finalSave: boolean; camParse: boolean };
  limits: { maxNodes: number; maxDepth: number; maxRequestBytes: number };
}
export type Scalar = string | number | boolean;
export type NodeRef = { $node: string };
export type ScalarItem = { itemId: string; value: Scalar };
export type FieldValue = Scalar | NodeRef | (NodeRef | ScalarItem)[];
export interface SchemaNode { nodeId: string; typeId: string; fields: Record<string, FieldValue> }
export interface AssetDraft { assetNodeId: string; elementNodeId: string; role: 'project' | 'machine' | 'material' | 'tool' | 'file' }
export interface ReferencePolicy {
  id: string; sourceType: string; fieldName: string; label: string;
  targetRole: AssetDraft['role']; targetType: string; editor: 'asset-picker' | 'nc-tools';
}
export interface ReferenceLink { sourceNodeId: string; policyId: string; targetAssetNodeId: string }
export interface FileLink { assetNodeId: string; fileId: string; sha256: string; purpose: 'NC' | 'STEP' | 'OTHER'; workplanNodeId: string | null }
export interface ToolLink { workplanNodeId: string; toolTag: string; assetNodeId: string; stepNodeIds: string[] }
export interface ManualAssignment { stepNodeId: string; toolTag: string; lineStart: number; lineEnd: number }
export interface NcReview { workplanNodeId: string; fileId: string; sha256: string; stepNodeIds: string[]; manual?: { mode: 'manual'; encoding: string; reason: string; snapshotHash: string; assignments: (ManualAssignment & { assetNodeId: string })[] } | null }
export interface ManualToolLink { workplanNodeId: string; stepNodeId: string; assetNodeId: string }
export interface CompletionEntry { nodeId: string; fieldName: string; value: FieldValue; kind: 'generated' | 'default' | 'placeholder' | 'batch'; rule: string; reason: string }
export interface Draft {
  draftVersion: 1; schemaVersion: string; schemaHash: string; rulesVersion: string;
  draftId: string; revision: number; nodes: Record<string, SchemaNode>;
  assets: AssetDraft[]; projectAssetNodeId: string;
  fileLinks?: FileLink[]; toolLinks?: ToolLink[]; ncReviews?: NcReview[];
  completionEntries?: CompletionEntry[];
  referenceLinks?: ReferenceLink[]; referencePolicyHash?: string | null;
  manualTools?: { assetNodeId: string; toolTypeId: string; legacyUnits?: boolean }[];
  manualToolLinks?: ManualToolLink[];
  manualWorkplans?: string[];
}
export interface Issue { nodeId: string | null; fieldName: string | null; itemId: string | null; code: string; message: string }
export interface Preview { valid: boolean; finalizable: false; issues: Issue[]; warnings?: Issue[]; pendingStorage?: Issue[]; artifacts: { assetNodeId: string; xml: string; reviewOnly?: boolean; omittedFields?: { nodeId: string; fieldName: string }[] }[] }
export function isRef(value: unknown): value is NodeRef {
  return typeof value === 'object' && value !== null && '$node' in value;
}
