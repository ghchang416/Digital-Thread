import type { Catalog, Draft, Preview } from '../schema/types';
import type { CamParseResult, CamSession, LocalFile } from '../../features/cam/types';
import type { NcAnalysis, ToolConflict } from '../../features/files/model';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v3/creator${url}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : body?.detail?.message ?? (response.status === 413 ? '요청 크기가 제한을 초과했습니다.' : `API 요청에 실패했습니다 (${response.status}).`));
  }
  return response.json() as Promise<T>;
}
export const fetchCatalog = () => request<Catalog>('/schema');
export interface ToolProfile {
  version: string; hash: string;
  toolTypes: { typeId: string; label: string }[];
  operationTypes: { typeId: string; label: string }[];
  properties: { name: string; field: string; label: string; unit: 'mm' | '1' | 'deg'; min: number; integer: boolean }[];
}
export interface ManualResult { ready: true; draft: Draft; assetNodeId?: string; stepNodeId?: string; persisted: false }
export const fetchToolProfile = () => request<ToolProfile>('/manual/profile');
export const prepareTool = (payload: object, signal: AbortSignal) => request<ManualResult>('/tools/prepare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal });
export const prepareManualStep = (payload: object, signal: AbortSignal) => request<ManualResult>('/workplans/manual-step', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal });
export const confirmManualNc = (payload: object, file: LocalFile, signal: AbortSignal) => ncRequest<ManualResult>('/nc/confirm', payload, file, signal);
export const completeWorkplan = (draft: Draft, workplanNodeId: string, includePlaceholders: boolean, overrides: Record<string, string | number | boolean>, signal: AbortSignal) => request<{ draft: Draft; addedCount: number; skipped: { nodeId: string; message: string }[] }>('/workplans/complete', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
  body: JSON.stringify({ draft, workplanNodeId, includePlaceholders, overrides, mode: 'missing-only' }),
});
export const reviewAsset = (draft: Draft, assetNodeId: string, signal?: AbortSignal) => request<Preview>('/review', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
  body: JSON.stringify({ mode: 'partial', draft, targetAssetNodeIds: [assetNodeId] }),
});

function ncRequest<T>(path: string, payload: object, file: LocalFile, signal: AbortSignal) {
  const form = new FormData(); form.append('payload', JSON.stringify(payload)); form.append(`file:${file.fileId}`, file.blob, file.name);
  return request<T>(path, { method: 'POST', body: form, signal });
}
export const analyzeNc = (file: LocalFile, encoding: string, signal: AbortSignal) => ncRequest<NcAnalysis>('/nc/analyze', { fileId: file.fileId, encoding }, file, signal);
export const compileNcTools = (payload: object, file: LocalFile, signal: AbortSignal) => ncRequest<{ ready: boolean; draft?: Draft; conflicts: ToolConflict[]; persisted: false }>('/nc/tools', payload, file, signal);

export function parseCam(catalog: Catalog, workplanNodeId: string, requestId: string, session: CamSession, files: Record<string, LocalFile>, signal: AbortSignal) {
  const form = new FormData();
  form.append('payload', JSON.stringify({ requestId, schemaHash: catalog.schemaHash, rulesVersion: catalog.rulesVersion,
    workplanNodeId, camType: session.camType, orderedFileIds: session.fileIds, mappingFileId: session.mappingFileId ?? null }));
  for (const id of [...session.fileIds, ...(session.mappingFileId ? [session.mappingFileId] : [])]) {
    const file = files[id];
    if (!file) throw new Error('CAM 원본 파일이 없습니다. 다시 선택해 주세요.');
    form.append(`file:${id}`, file.blob, file.name);
  }
  return request<CamParseResult>('/cam/parse', { method: 'POST', body: form, signal });
}
