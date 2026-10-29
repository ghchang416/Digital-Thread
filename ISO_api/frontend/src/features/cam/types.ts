import type { FieldValue, SchemaNode } from '../../shared/schema/types';

export type CamType = 'nx' | 'powermill';
export interface LocalFile { fileId: string; name: string; size: number; sha256: string; blob: Blob }
export interface CamOrigin { nodeId: string; fieldName: string; sourcePath: string; targetPath: string; value: FieldValue }
export interface CamDiagnostic { code: string; message: string; sourcePath: string | null; nodeId: string | null; fieldName: string | null }
export interface CamCandidate {
  candidateId: string; fileId: string; sourceIndex: number; title: string; rootNodeId: string;
  nodes: Record<string, SchemaNode>; origins: CamOrigin[]; diagnostics: CamDiagnostic[];
  unmappedPaths: string[]; unmappedCount: number; importable: boolean;
}
export interface CamParseResult {
  requestId: string; workplanNodeId: string; camType: CamType; parserVersion: string; mappingHash: string;
  mapping: Record<string, string>; fileResults: { fileId: string; name: string; sha256: string; operationCount: number; error: string | null }[];
  operations: CamCandidate[]; partial: boolean; persisted: false;
}
export interface CamSession {
  camType: CamType; fileIds: string[]; mappingFileId?: string; pasteName: string; pasteText: string;
  result?: CamParseResult; selectedIds: string[]; names: Record<string, string>; acknowledged: boolean;
}
export interface CamImport {
  importId: string; workplanNodeId: string; camType: CamType; parserVersion: string; mappingHash: string;
  mapping: Record<string, string>; fileResults: CamParseResult['fileResults']; candidates: CamCandidate[]; appliedAt: string;
}
export const emptyCamSession = (): CamSession => ({ camType: 'nx', fileIds: [], pasteName: '', pasteText: '', selectedIds: [], names: {}, acknowledged: false });
