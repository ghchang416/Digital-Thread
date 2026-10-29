import { isRef } from '../../shared/schema/types';
import type { CompletionEntry, Draft, FieldValue, Issue } from '../../shared/schema/types';
import type { StructureRow } from '../../shared/draft/structure';

export const completionLabels: Record<CompletionEntry['kind'], string> = { generated: '자동 생성', default: '기본값', placeholder: '임시값', batch: '공통 입력' };
export interface CompletionSettings { includePlaceholders: boolean; values: Record<string, string> }
export const emptySettings = (): CompletionSettings => ({ includePlaceholders: false, values: {} });
export function workplanSteps(draft: Draft, id: string): string[] {
  const elements = draft.nodes[id]?.fields.its_elements;
  return Array.isArray(elements) ? elements.filter(isRef).map(ref => ref.$node).filter(id => draft.nodes[id]?.typeId === 'MachiningWorkingstep') : [];
}
export function formatValue(value: FieldValue | undefined, draft: Draft): string {
  if (value === undefined) return '값 없음';
  if (isRef(value)) {
    const node = draft.nodes[value.$node];
    return String(node?.fields.its_id || node?.fields.name || node?.typeId || '객체');
  }
  if (Array.isArray(value)) return value.map(item => isRef(item) ? formatValue(item, draft) : String(item.value)).join(', ');
  return String(value);
}
export function groupIssues(issues: Issue[], rows: StructureRow[], draft: Draft) {
  const lookup = new Map<string, StructureRow>();
  for (const row of rows) if (!lookup.has(row.nodeId)) lookup.set(row.nodeId, row);
  const groups = new Map<string, { title: string; issues: (Issue & { context: string })[] }>();
  for (const issue of issues) {
    const row = lookup.get(issue.nodeId ?? '');
    const path = row?.path ?? [];
    const owner = [...path].reverse().find(id => ['MachiningWorkingstep', 'TurningWorkingstep', 'Workplan'].includes(draft.nodes[id]?.typeId));
    const wp = path.filter(id => draft.nodes[id]?.typeId === 'Workplan');
    const asset = draft.assets?.find(item => item.assetNodeId === (row?.assetId ?? issue.nodeId));
    const element = asset && draft.nodes[asset.elementNodeId];
    const assetTitle = element ? String(element.fields.display_name || element.fields.path || element.fields.element_id || row?.title || element.typeId) : '자산 · 프로젝트';
    const title = [...wp, ...(owner && !wp.includes(owner) ? [owner] : [])].map(id => String(draft.nodes[id].fields.its_id || draft.nodes[id].typeId)).join(' / ') || assetTitle;
    const key = owner ?? row?.assetId ?? 'asset';
    const group = groups.get(key) ?? { title, issues: [] };
    const relations = path.slice(owner ? path.indexOf(owner) + 1 : 0).map(id => lookup.get(id)?.relation).filter(Boolean).join(' / ');
    group.issues.push({ ...issue, context: row ? `${relations || row.relation} · ${row.typeLabel}` : '' });
    groups.set(key, group);
  }
  return [...groups.entries()].map(([key, value]) => ({ key, ...value }));
}
