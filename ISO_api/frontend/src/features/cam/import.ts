import type { Draft } from '../../shared/schema/types';
import { isRef } from '../../shared/schema/types';
import { newId } from '../../shared/draft/model';
import type { CamImport, CamSession, LocalFile } from './types';

export async function makeLocalFile(file: Blob, name: string): Promise<LocalFile> {
  if (!file.size || file.size > 8 * 1024 * 1024) throw new Error('비어 있지 않은 8 MiB 이하 파일을 선택해 주세요.');
  const bytes = await file.arrayBuffer();
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return { fileId: newId(), name, size: file.size, blob: file,
    sha256: [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join('') };
}

export function applyCamImport(draft: Draft, workplanId: string, session: CamSession, imports: CamImport[]): { draft: Draft; entry: CamImport } {
  const result = session.result;
  const parent = draft.nodes[workplanId];
  if (!result || result.workplanNodeId !== workplanId || result.camType !== session.camType || parent?.typeId !== 'Workplan') throw new Error('대상 워크플랜과 파싱 결과를 다시 확인해 주세요.');
  if (!session.acknowledged) throw new Error('파싱 결과와 누락 항목을 확인해 주세요.');
  const selected = session.selectedIds.map(id => result.operations.find(op => op.candidateId === id));
  if (!selected.length || selected.some(op => !op?.importable) || new Set(session.selectedIds).size !== session.selectedIds.length) throw new Error('추가할 작업을 선택해 주세요.');
  const candidates = selected.filter(op => !!op);
  const existingIds = new Set(Object.values(draft.nodes).filter(node => node.typeId === 'MachiningWorkingstep').map(node => node.fields.its_id));
  const nodes = { ...draft.nodes };
  const existing = parent.fields.its_elements;
  if (existing !== undefined && (!Array.isArray(existing) || !existing.every(isRef))) throw new Error('워크플랜 실행 요소 형식을 확인해 주세요.');
  for (const candidate of candidates) {
    const name = (session.names[candidate.candidateId] ?? String(candidate.nodes[candidate.rootNodeId].fields.its_id ?? '')).trim();
    if (!name) throw new Error('모든 워킹스텝의 식별자를 입력해 주세요.');
    if (existingIds.has(name)) throw new Error(`워킹스텝 식별자가 중복됩니다: ${name}`);
    existingIds.add(name);
    const hash = result.fileResults.find(file => file.fileId === candidate.fileId)?.sha256;
    if (!hash) throw new Error('CAM 원본 해시를 확인할 수 없습니다.');
    if (imports.some(entry => entry.workplanNodeId === workplanId && entry.camType === result.camType && entry.candidates.some(previous =>
      draft.nodes[previous.rootNodeId] && previous.sourceIndex === candidate.sourceIndex && entry.fileResults.find(file => file.fileId === previous.fileId)?.sha256 === hash))) {
      throw new Error('이 원본 작업은 이미 해당 워크플랜에 있습니다. 기존 항목을 편집하거나 삭제한 뒤 다시 가져와 주세요.');
    }
    if (Object.keys(candidate.nodes).some(id => nodes[id])) throw new Error('이미 적용된 파싱 결과입니다.');
    for (const [id, node] of Object.entries(candidate.nodes)) nodes[id] = structuredClone(node);
    nodes[candidate.rootNodeId].fields.its_id = name;
  }
  if (Object.keys(nodes).length > 10000) throw new Error('프로젝트 객체 수 제한을 초과했습니다.');
  nodes[workplanId] = { ...parent, fields: { ...parent.fields, its_elements: [...(Array.isArray(existing) ? existing : []), ...candidates.map(op => ({ $node: op.rootNodeId }))] } };
  return {
    draft: { ...draft, nodes, revision: draft.revision + 1 },
    entry: { importId: newId(), workplanNodeId: workplanId, camType: result.camType, parserVersion: result.parserVersion,
      mappingHash: result.mappingHash, mapping: result.mapping, fileResults: result.fileResults, candidates: structuredClone(candidates), appliedAt: new Date().toISOString() },
  };
}
