import type { Draft, FileLink, ManualAssignment } from '../../shared/schema/types';
import { isRef } from '../../shared/schema/types';
import { addAsset } from '../../shared/draft/model';
import type { LocalFile } from '../cam/types';

export interface NcEvent { eventId: string; toolTag: string; lineStart: number; lineEnd: number; source: string }
export interface NcAnalysis { fileId: string; sha256: string; encoding: string; events: NcEvent[]; diagnostics: string[]; supported: boolean; persisted: false }
export interface NcSession { encoding: 'utf-8' | 'cp949'; analysis?: NcAnalysis; assignments: Record<string, string>; resolutions: Record<string, Record<string, number>>; appliedSignature?: string; manualRows?: Record<string, ManualAssignment>; manualReason?: string }
export interface ToolConflict { toolTag: string; property: string; choices: { label: string; value: number }[] }
export const emptyNcSession = (): NcSession => ({ encoding: 'utf-8', assignments: {}, resolutions: {} });
export function directSteps(draft: Draft, workplanId: string): string[] {
  const refs = draft.nodes[workplanId]?.fields.its_elements;
  return (Array.isArray(refs) ? refs : []).filter(isRef).map(ref => ref.$node).filter(id => ['MachiningWorkingstep', 'TurningWorkingstep'].includes(draft.nodes[id]?.typeId));
}
export function addFileAsset(draft: Draft, file: LocalFile, purpose: FileLink['purpose']): Draft {
  const next = addAsset(draft, 'file', 'DtFile');
  const asset = next.assets.at(-1)!;
  const globalId = draft.nodes[draft.projectAssetNodeId]?.fields.asset_global_id;
  next.nodes[asset.assetNodeId].fields = { ...next.nodes[asset.assetNodeId].fields, id: `file_${file.fileId.slice(0, 8)}`, asset_kind: 'instance', ...(globalId ? { asset_global_id: globalId } : {}) };
  next.nodes[asset.elementNodeId].fields = { element_id: `file_${file.fileId.slice(0, 8)}`, display_name: file.name, category: purpose,
    content_type: purpose === 'NC' ? 'text/x-gcode' : purpose === 'STEP' ? 'application/step' : file.blob.type || 'application/octet-stream', path: file.name };
  next.fileLinks = [...(draft.fileLinks ?? []), { assetNodeId: asset.assetNodeId, fileId: file.fileId, sha256: file.sha256, purpose, workplanNodeId: null }];
  return next;
}
export function bindFile(draft: Draft, assetId: string, workplanId: string | null): Draft {
  const link = draft.fileLinks?.find(item => item.assetNodeId === assetId);
  if (!link || (workplanId && draft.nodes[workplanId]?.typeId !== 'Workplan')) throw new Error('파일 또는 대상 워크플랜을 확인해 주세요.');
  if (workplanId && link.purpose === 'NC' && draft.fileLinks?.some(item => item.assetNodeId !== assetId && item.purpose === 'NC' && item.workplanNodeId === workplanId)) throw new Error('워크플랜에는 실행용 NC 파일을 하나만 배정할 수 있습니다.');
  return { ...draft, revision: draft.revision + 1, fileLinks: draft.fileLinks?.map(item => item.assetNodeId === assetId ? { ...item, workplanNodeId: workplanId } : item) };
}
export function ncSignature(draft: Draft, workplanId: string, session: NcSession): string {
  const visited = new Set<string>();
  const stack = [...directSteps(draft, workplanId), ...(draft.toolLinks ?? []).filter(link => link.workplanNodeId === workplanId).map(link => link.assetNodeId), ...(draft.manualToolLinks ?? []).filter(link => link.workplanNodeId === workplanId).map(link => link.assetNodeId)];
  while (stack.length) {
    const id = stack.pop()!;
    if (visited.has(id) || !draft.nodes[id]) continue;
    visited.add(id);
    for (const value of Object.values(draft.nodes[id].fields)) for (const item of Array.isArray(value) ? value : [value]) if (isRef(item)) stack.push(item.$node);
  }
  return JSON.stringify({ elements: draft.nodes[workplanId]?.fields.its_elements, file: draft.fileLinks?.filter(link => link.workplanNodeId === workplanId && link.purpose === 'NC'),
    nodes: [...visited].sort().map(id => draft.nodes[id]), assignments: session.assignments, encoding: session.encoding,
    ...(draft.manualWorkplans?.includes(workplanId) ? { manualLinks: draft.manualToolLinks?.filter(link => link.workplanNodeId === workplanId), manualRows: session.manualRows, manualReason: session.manualReason, manualTools: draft.manualTools } : {}) });
}
