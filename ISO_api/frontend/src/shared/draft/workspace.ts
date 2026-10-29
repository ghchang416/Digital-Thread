import type { AssetDraft, Catalog, Draft } from '../schema/types';
import { isRef } from '../schema/types';
import { initialDraft } from './model';
import { referenceRecoveryError } from './references';
import type { CamImport, CamSession, LocalFile } from '../../features/cam/types';
import type { NcSession } from '../../features/files/model';
import type { CompletionSettings } from '../../features/completion/model';
import { manualRecoveryError } from '../../features/manual/model';

export interface WorkspaceData {
  screen?: 'operator' | 'detail' | 'export' | 'settings';
  draft: Draft;
  role: AssetDraft['role']; assetId: string; path: string[];
  rawInputs: Record<string, string>; extraFields: Record<string, string[]>;
  camSessions: Record<string, CamSession>; camImports: CamImport[]; files: Record<string, LocalFile>;
  ncSessions?: Record<string, NcSession>;
  completionSettings?: Record<string, CompletionSettings>;
}
export interface RecoveryRecord { formatVersion: 1; sequence: number; savedAt: string; data: WorkspaceData }
export function initialWorkspace(catalog: Catalog): WorkspaceData {
  const draft = initialDraft(catalog);
  return { draft, role: 'project', assetId: draft.projectAssetNodeId, path: [], rawInputs: {}, extraFields: {}, camSessions: {}, camImports: [], files: {} };
}

export function validateRecovery(record: RecoveryRecord, catalog: Catalog): void {
  if (record?.formatVersion !== 1 || !Number.isSafeInteger(record.sequence) || record.sequence < 1 || !record.data?.draft) throw new Error('로컬 초안 형식을 확인할 수 없습니다. 기존 데이터는 보존했습니다.');
  const data = record.data;
  if (data.screen !== undefined && !['operator', 'detail', 'export', 'settings'].includes(data.screen)) throw new Error('로컬 화면 상태가 올바르지 않습니다.');
  const draft = data.draft;
  if (draft.schemaHash !== catalog.schemaHash || draft.rulesVersion !== catalog.rulesVersion || draft.draftVersion !== 1) throw new Error('로컬 초안의 스키마 버전이 현재 서버와 다릅니다. 기존 데이터는 보존했습니다.');
  if (!draft.nodes || !Array.isArray(draft.assets) || !draft.nodes[draft.projectAssetNodeId] || Object.keys(draft.nodes).length > 10000) throw new Error('로컬 초안의 자산 구조가 올바르지 않습니다.');
  const unsafe = new Set(['__proto__', 'constructor', 'prototype']);
  const scalar = (value: unknown) => typeof value === 'string' || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value));
  for (const [id, node] of Object.entries(draft.nodes)) {
    if (!node || unsafe.has(id) || id !== node.nodeId || !catalog.types[node.typeId] || !node.fields) throw new Error('로컬 객체 타입을 확인할 수 없습니다.');
    for (const [name, value] of Object.entries(node.fields)) {
      if (unsafe.has(name) || !catalog.types[node.typeId].fields.some(field => field.fieldName === name)) throw new Error('로컬 초안에 알 수 없는 필드가 있습니다.');
      for (const item of Array.isArray(value) ? value : [value]) {
        if (isRef(item) && !draft.nodes[item.$node]) throw new Error('로컬 초안의 연결 객체가 누락되었습니다.');
        if (!isRef(item) && !scalar(item) && !(Array.isArray(value) && typeof item === 'object' && item && 'itemId' in item && typeof item.itemId === 'string' && scalar(item.value))) throw new Error('로컬 초안의 값 형식이 손상되었습니다.');
      }
    }
  }
  for (const asset of draft.assets) if (!draft.nodes[asset.assetNodeId] || !draft.nodes[asset.elementNodeId]) throw new Error('로컬 자산이 누락되었습니다.');
  const referenceError = referenceRecoveryError(draft, catalog);
  if (referenceError) throw new Error(referenceError);
  const manualError = manualRecoveryError(draft);
  if (manualError) throw new Error(manualError);
  if (draft.completionEntries !== undefined && (!Array.isArray(draft.completionEntries) || draft.completionEntries.length > 20000)) throw new Error('로컬 보완 이력이 손상되었습니다.');
  for (const entry of draft.completionEntries ?? []) {
    if (!entry || typeof entry.nodeId !== 'string' || typeof entry.fieldName !== 'string' || !['generated', 'default', 'placeholder', 'batch'].includes(entry.kind) || typeof entry.reason !== 'string' || typeof entry.rule !== 'string') throw new Error('로컬 보완 이력이 손상되었습니다.');
    for (const item of Array.isArray(entry.value) ? entry.value : [entry.value]) if (!scalar(item) && !(isRef(item) && typeof item.$node === 'string') && !(Array.isArray(entry.value) && typeof item === 'object' && item && 'itemId' in item && typeof item.itemId === 'string' && scalar(item.value))) throw new Error('로컬 보완 값이 손상되었습니다.');
  }
  for (const settings of Object.values(data.completionSettings ?? {})) if (typeof settings.includePlaceholders !== 'boolean' || !settings.values || !Object.values(settings.values).every(value => typeof value === 'string')) throw new Error('로컬 보완 설정이 손상되었습니다.');
  if (!['project', 'machine', 'material', 'file', 'tool'].includes(data.role) || !Array.isArray(data.path) || !data.rawInputs || !data.extraFields || !data.camSessions || !Array.isArray(data.camImports) || !data.files) throw new Error('로컬 편집 상태가 올바르지 않습니다.');
  if (!Object.values(data.rawInputs).every(value => typeof value === 'string') || !Object.values(data.extraFields).every(value => Array.isArray(value) && value.every(name => typeof name === 'string'))) throw new Error('로컬 입력 상태가 손상되었습니다.');
  for (const [id, file] of Object.entries(data.files)) if (id !== file.fileId || !(file.blob instanceof Blob) || file.size !== file.blob.size) throw new Error('로컬 CAM 원본 파일이 누락되었거나 손상되었습니다.');
  for (const session of Object.values(data.camSessions)) {
    if (!['nx', 'powermill'].includes(session.camType) || !Array.isArray(session.fileIds) || !Array.isArray(session.selectedIds) || !session.names) throw new Error('로컬 CAM 편집 상태가 올바르지 않습니다.');
    for (const id of [...session.fileIds, ...(session.mappingFileId ? [session.mappingFileId] : [])]) if (!data.files[id]) throw new Error('CAM 원본 파일을 복구할 수 없습니다.');
    if (session.result && (!Array.isArray(session.result.operations) || !Array.isArray(session.result.fileResults))) throw new Error('CAM 파싱 결과를 복구할 수 없습니다.');
  }
  for (const entry of data.camImports) {
    if (!Array.isArray(entry.candidates) || !Array.isArray(entry.fileResults)) throw new Error('CAM 원본 이력이 손상되었습니다.');
    for (const candidate of entry.candidates) if (!candidate.nodes?.[candidate.rootNodeId] || !Array.isArray(candidate.origins) || !data.files[candidate.fileId]) throw new Error('CAM 원본 이력을 복구할 수 없습니다.');
  }
  for (const link of draft.fileLinks ?? []) if (!data.files[link.fileId] || data.files[link.fileId].sha256 !== link.sha256 || !draft.assets.some(asset => asset.assetNodeId === link.assetNodeId && asset.role === 'file')) throw new Error('파일 자산의 로컬 원본이 누락되었습니다.');
  for (const session of Object.values(data.ncSessions ?? {})) {
    if (!session.assignments || !session.resolutions || !['utf-8', 'cp949'].includes(session.encoding)) throw new Error('NC 연결 상태가 손상되었습니다.');
    if (session.manualReason !== undefined && (typeof session.manualReason !== 'string' || session.manualReason.length > 1000)) throw new Error('NC 수동 확인 사유가 손상되었습니다.');
    if (session.manualRows !== undefined) {
      if (!session.manualRows || typeof session.manualRows !== 'object' || Array.isArray(session.manualRows) || Object.keys(session.manualRows).length > 1000) throw new Error('NC 수동 배정이 손상되었습니다.');
      for (const [id, row] of Object.entries(session.manualRows)) {
        // Unfinished fields (including an empty T or zero row) must remain recoverable.
        if (!row || row.stepNodeId !== id || typeof row.toolTag !== 'string' || !Number.isFinite(row.lineStart) || !Number.isFinite(row.lineEnd)) throw new Error('NC 수동 배정 값이 손상되었습니다.');
      }
    }
  }
}
