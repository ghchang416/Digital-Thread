import { isRef } from '../schema/types';
import type { AssetDraft, Catalog, Draft, FieldValue, SchemaNode } from '../schema/types';
import { assetReferenceUsers } from './references';

export const newId = () => crypto.randomUUID();
export function blankNode(typeId: string): SchemaNode { return { nodeId: newId(), typeId, fields: {} }; }

export function addAsset(draft: Draft, role: AssetDraft['role'], typeId: string): Draft {
  const root = blankNode('DtAsset');
  const element = blankNode(typeId);
  root.fields = { asset_global_id: 'https://digital-thread.re/kitech/', schema_version: draft.schemaVersion, dt_elements: [{ $node: element.nodeId }] };
  const nodes = { ...draft.nodes, [root.nodeId]: root, [element.nodeId]: element };
  if (typeId === 'DtProject') {
    const workplan = blankNode('Workplan');
    nodes[workplan.nodeId] = workplan;
    element.fields.main_workplan = { $node: workplan.nodeId };
  }
  return { ...draft, revision: draft.revision + 1, nodes,
    projectAssetNodeId: role === 'project' ? root.nodeId : draft.projectAssetNodeId,
    assets: [...draft.assets, { assetNodeId: root.nodeId, elementNodeId: element.nodeId, role }] };
}
export function initialDraft(catalog: Catalog): Draft {
  return addAsset({ draftVersion: 1, schemaVersion: catalog.schemaVersion ?? 'v31', schemaHash: catalog.schemaHash,
    rulesVersion: catalog.rulesVersion, draftId: newId(), revision: 0, nodes: {}, assets: [], projectAssetNodeId: '' }, 'project', 'DtProject');
}

export type Command =
  | { kind: 'reference'; nodeId: string; policyId: string; targetAssetNodeId?: string; policyHash: string }
  | { kind: 'set'; nodeId: string; field: string; value?: FieldValue }
  | { kind: 'attach'; nodeId: string; field: string; typeId: string; repeated: boolean }
  | { kind: 'remove-item'; nodeId: string; field: string; index: number }
  | { kind: 'move'; nodeId: string; field: string; index: number; direction: -1 | 1 }
  | { kind: 'asset'; role: AssetDraft['role']; typeId: string }
  | { kind: 'delete-asset'; assetNodeId: string };

function prune(draft: Draft): Draft {
  const visited = new Set<string>();
  const stack = draft.assets.map(asset => asset.assetNodeId);
  while (stack.length) {
    const id = stack.pop()!;
    if (visited.has(id)) continue;
    visited.add(id);
    const node = draft.nodes[id];
    if (!node) continue;
    for (const value of Object.values(node.fields)) {
      const items = Array.isArray(value) ? value : [value];
      for (const item of items) if (isRef(item)) stack.push(item.$node);
    }
  }
  return { ...draft, ...(draft.manualToolLinks ? { manualToolLinks: draft.manualToolLinks.filter(link => visited.has(link.stepNodeId) && visited.has(link.workplanNodeId)) } : {}), ...(draft.manualWorkplans ? { manualWorkplans: draft.manualWorkplans.filter(id => visited.has(id)) } : {}), ...(draft.manualTools ? { manualTools: draft.manualTools.filter(tool => visited.has(tool.assetNodeId)) } : {}), ...(draft.referenceLinks ? { referenceLinks: draft.referenceLinks.filter(link => visited.has(link.sourceNodeId)) } : {}), ...(draft.completionEntries ? { completionEntries: draft.completionEntries.filter(entry => visited.has(entry.nodeId)) } : {}), nodes: Object.fromEntries(Object.entries(draft.nodes).filter(([id]) => visited.has(id))) };
}

export function applyCommand(draft: Draft, command: Command): Draft {
  if (command.kind === 'asset') {
    if (command.role === 'project') return draft;
    return addAsset(draft, command.role, command.typeId);
  }
  if (command.kind === 'delete-asset') {
    if (command.assetNodeId === draft.projectAssetNodeId) return draft;
    if (assetReferenceUsers(draft, command.assetNodeId).length) return draft;
    if (draft.manualToolLinks?.some(link => link.assetNodeId === command.assetNodeId && draft.nodes[link.stepNodeId])) return draft;
    if (draft.toolLinks?.some(link => link.assetNodeId === command.assetNodeId && link.stepNodeIds.some(id => draft.nodes[id]))) return draft;
    return prune({ ...draft, revision: draft.revision + 1, assets: draft.assets.filter(a => a.assetNodeId !== command.assetNodeId), fileLinks: draft.fileLinks?.filter(link => link.assetNodeId !== command.assetNodeId), toolLinks: draft.toolLinks?.filter(link => link.assetNodeId !== command.assetNodeId) });
  }
  const previous = draft.nodes[command.nodeId];
  if (!previous) return draft;
  if (command.kind === 'reference') {
    const links = (draft.referenceLinks ?? []).filter(link => link.sourceNodeId !== command.nodeId || link.policyId !== command.policyId);
    if (command.targetAssetNodeId) links.push({ sourceNodeId: command.nodeId, policyId: command.policyId, targetAssetNodeId: command.targetAssetNodeId });
    return { ...draft, revision: draft.revision + 1, referenceLinks: links, referencePolicyHash: command.policyHash };
  }
  const node = { ...previous, fields: { ...previous.fields } };
  const nodes = { ...draft.nodes, [node.nodeId]: node };
  if (command.kind === 'set') {
    if (command.value === undefined) delete node.fields[command.field];
    else node.fields[command.field] = command.value;
  } else if (command.kind === 'attach') {
    const child = blankNode(command.typeId);
    nodes[child.nodeId] = child;
    const old = node.fields[command.field];
    node.fields[command.field] = command.repeated ? [...(Array.isArray(old) ? old : []), { $node: child.nodeId }] : { $node: child.nodeId };
  } else {
    const old = node.fields[command.field];
    if (!Array.isArray(old) || command.index < 0 || command.index >= old.length) return draft;
    const items = [...old];
    if (command.kind === 'remove-item') items.splice(command.index, 1);
    else {
      const to = command.index + command.direction;
      if (to < 0 || to >= items.length) return draft;
      [items[command.index], items[to]] = [items[to], items[command.index]];
    }
    node.fields[command.field] = items;
  }
  return prune({ ...draft, nodes, revision: draft.revision + 1 });
}

export function nodeTitle(node: SchemaNode, catalog: Catalog): string {
  for (const key of ['display_name', 'its_id', 'element_id', 'parameter_name', 'description']) {
    const value = node.fields[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return catalog.types[node.typeId]?.label ?? node.typeId;
}
