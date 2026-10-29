import { addAsset, applyCommand, blankNode } from '../../shared/draft/model';
import { initialWorkspace } from '../../shared/draft/workspace';
import type { AssetDraft, Catalog, Draft } from '../../shared/schema/types';
import { isRef } from '../../shared/schema/types';

export const preferencesKey = 'dt-project-creator.preferences.v1';
export interface Preferences { version: 1; uriPrefix: string; defaultMode: 'operator' | 'detail' }
export const defaultPreferences: Preferences = { version: 1, uriPrefix: 'https://digital-thread.re/kitech/', defaultMode: 'operator' };
export function validatePreferences(value: Preferences): Preferences {
  if (value.version !== 1 || !['operator', 'detail'].includes(value.defaultMode) || typeof value.uriPrefix !== 'string' || /\s|%(?![0-9a-f]{2})/i.test(value.uriPrefix)) throw new Error('설정 형식을 확인해 주세요.');
  const url = new URL(value.uriPrefix);
  if (!['http:', 'https:'].includes(url.protocol) || url.search || url.hash || url.username || url.password) throw new Error('쿼리·인증 정보 없는 HTTP(S) 주소를 입력해 주세요.');
  return { version: 1, uriPrefix: url.href.replace(/\/*$/, '/'), defaultMode: value.defaultMode };
}
export function readPreferences(): Preferences {
  const raw = localStorage.getItem(preferencesKey);
  return raw ? validatePreferences(JSON.parse(raw)) : defaultPreferences;
}
export function identifyAsset(draft: Draft, asset: AssetDraft, prefix: string): Draft {
  const token = `${asset.role}_${asset.assetNodeId.replace(/-/g, '')}`;
  const root = draft.nodes[asset.assetNodeId]; const element = draft.nodes[asset.elementNodeId];
  const global = asset.role === 'project' ? `${prefix}${token}` : draft.nodes[draft.projectAssetNodeId].fields.asset_global_id;
  return { ...draft, nodes: { ...draft.nodes,
    [root.nodeId]: { ...root, fields: { ...root.fields, id: token, asset_kind: 'instance', asset_global_id: global } },
    [element.nodeId]: { ...element, fields: { ...element.fields, element_id: token, ...(asset.role === 'project' ? { its_id: token } : {}) } },
  } };
}
export function newWorkspace(catalog: Catalog, preferences: Preferences) {
  const data = initialWorkspace(catalog);
  data.draft = identifyAsset(data.draft, data.draft.assets[0], preferences.uriPrefix);
  const ref = data.draft.nodes[data.draft.assets[0].elementNodeId].fields.main_workplan;
  if (isRef(ref)) data.draft = applyCommand(data.draft, { kind: 'set', nodeId: ref.$node, field: 'its_id', value: '메인 워크플랜' });
  data.screen = preferences.defaultMode;
  return data;
}
export function createAsset(draft: Draft, role: 'machine' | 'material') {
  const next = addAsset(draft, role, role === 'machine' ? 'DtMachineTool' : 'DtMaterial');
  const asset = next.assets.at(-1)!;
  next.nodes[asset.elementNodeId].fields.display_name = '';
  return identifyAsset(next, asset, defaultPreferences.uriPrefix);
}
export function addWorkplan(draft: Draft, parentId: string): Draft {
  const parent = draft.nodes[parentId];
  if (parent?.typeId !== 'Workplan') return draft;
  const child = blankNode('Workplan');
  child.fields = { its_id: `워크플랜 ${Object.values(draft.nodes).filter(n => n.typeId === 'Workplan').length}`, its_elements: [] };
  const elements = parent.fields.its_elements;
  return { ...draft, revision: draft.revision + 1, nodes: { ...draft.nodes, [child.nodeId]: child,
    [parentId]: { ...parent, fields: { ...parent.fields, its_elements: [...(Array.isArray(elements) ? elements : []), { $node: child.nodeId }] } } } };
}
