import type { Draft } from '../../shared/schema/types';
import { isRef } from '../../shared/schema/types';

export function toolInputValues(draft: Draft, assetId?: string): Record<string, { value: string; unit: string }> {
  const asset = draft.assets.find(a => a.assetNodeId === assetId);
  const refs = asset && draft.nodes[asset.elementNodeId]?.fields.numerical_value;
  const values: Record<string, { value: string; unit: string }> = {};
  for (const ref of Array.isArray(refs) ? refs : []) {
    if (!isRef(ref)) continue;
    const fields = draft.nodes[ref.$node]?.fields;
    if (!fields || typeof fields.value_name !== 'string') continue;
    const unit = fields.unit_component;
    values[fields.value_name] = { value: String(fields.value_component ?? ''), unit: isRef(unit) ? String(draft.nodes[unit.$node]?.fields.unit_name ?? '') : '' };
  }
  if (draft.manualTools?.find(t => t.assetNodeId === assetId)?.legacyUnits && values.overhang_length && !values.assembly_length) values.assembly_length = { ...values.overhang_length, unit: 'mm' };
  return values;
}

export function manualRecoveryError(draft: Draft): string | undefined {
  if (draft.manualTools !== undefined && (!Array.isArray(draft.manualTools) || draft.manualTools.length > 1000)) return '수동 공구 정보가 손상되었습니다.';
  if (draft.manualWorkplans !== undefined && (!Array.isArray(draft.manualWorkplans) || draft.manualWorkplans.length > 1000 || new Set(draft.manualWorkplans).size !== draft.manualWorkplans.length)) return '수동 워크플랜 정보가 손상되었습니다.';
  if (draft.manualToolLinks !== undefined && (!Array.isArray(draft.manualToolLinks) || draft.manualToolLinks.length > 1000)) return '수동 공구 연결이 손상되었습니다.';
  const ids = new Set<string>();
  for (const id of draft.manualWorkplans ?? []) if (typeof id !== 'string' || draft.nodes[id]?.typeId !== 'Workplan') return '수동 워크플랜이 누락되었습니다.';
  for (const tool of draft.manualTools ?? []) {
    if (!tool || typeof tool.toolTypeId !== 'string' || (tool.legacyUnits !== undefined && typeof tool.legacyUnits !== 'boolean') || ids.has(tool.assetNodeId) || !draft.assets.some(a => a.assetNodeId === tool.assetNodeId && a.role === 'tool' && draft.nodes[a.elementNodeId]?.typeId === 'DtCuttingTool13399')) return '수동 공구 자산이 누락되거나 중복되었습니다.';
    ids.add(tool.assetNodeId);
  }
  const seen = new Set<string>();
  for (const link of draft.manualToolLinks ?? []) {
    const wp = link && draft.nodes[link.workplanNodeId];
    if (!link || !wp || wp.typeId !== 'Workplan' || !['MachiningWorkingstep', 'TurningWorkingstep'].includes(draft.nodes[link.stepNodeId]?.typeId) || !draft.manualWorkplans?.includes(link.workplanNodeId) || !ids.has(link.assetNodeId) || seen.has(link.stepNodeId) || !Array.isArray(wp.fields.its_elements) || !wp.fields.its_elements.some(ref => isRef(ref) && ref.$node === link.stepNodeId)) return '수동 공구의 워킹스텝 연결을 확인해 주세요.';
    seen.add(link.stepNodeId);
  }
}
