import { nodeTitle } from './model';
import { isRef } from '../schema/types';
import type { AssetDraft, Catalog, Draft } from '../schema/types';

export interface StructureRow {
  key: string;
  parentKey: string | null;
  assetId: string;
  nodeId: string;
  path: string[];
  depth: number;
  title: string;
  typeLabel: string;
  relation: string;
  childCount: number;
  position: number;
  siblingCount: number;
}

export function structureKey(assetId: string, path: string[]): string {
  return JSON.stringify([assetId, ...path]);
}

// Only instantiated objects belong in the outline; scalar values stay in the editor.
export function buildStructure(draft: Draft, catalog: Catalog, assets: AssetDraft[]): StructureRow[] {
  const rows: StructureRow[] = [];
  function visit(assetId: string, id: string, parents: string[], parentKey: string | null, relation: string, position: number, siblingCount: number) {
    const node = draft.nodes[id];
    if (!node || parents.includes(id) || parents.length >= 64 || rows.length >= 10000) return;
    const path = [...parents, id];
    const type = catalog.types[node.typeId];
    const children: { id: string; relation: string }[] = [];
    const seen = new Set<string>();
    for (const [name, value] of Object.entries(node.fields)) {
      const field = type?.fields.find(f => f.fieldName === name);
      const values = Array.isArray(value) ? value : [value];
      values.forEach((item, index) => {
        if (!isRef(item) || !draft.nodes[item.$node] || path.includes(item.$node) || seen.has(item.$node)) return;
        seen.add(item.$node);
        children.push({ id: item.$node, relation: `${field?.label ?? name}${Array.isArray(value) ? ` ${index + 1}` : ''}` });
      });
    }
    const row: StructureRow = { key: structureKey(assetId, path), parentKey, assetId, nodeId: id, path,
      depth: parents.length, title: nodeTitle(node, catalog), typeLabel: type?.label ?? node.typeId,
      relation, childCount: children.length, position, siblingCount };
    rows.push(row);
    children.forEach((child, index) => visit(assetId, child.id, path, row.key, child.relation, index + 1, children.length));
  }
  assets.forEach((asset, index) => visit(asset.assetNodeId, asset.elementNodeId, [], null, '자산', index + 1, assets.length));
  return rows;
}

export function visibleStructure(rows: StructureRow[], expanded: Record<string, boolean>, query: string): StructureRow[] {
  const term = query.trim().toLocaleLowerCase();
  if (term) {
    const included = new Set<string>();
    for (const row of rows) {
      if (!`${row.title} ${row.typeLabel} ${row.relation}`.toLocaleLowerCase().includes(term)) continue;
      for (let i = 1; i <= row.path.length; i++) included.add(structureKey(row.assetId, row.path.slice(0, i)));
    }
    return rows.filter(row => included.has(row.key));
  }
  const open = new Set<string>();
  return rows.filter(row => {
    const visible = row.parentKey === null || open.has(row.parentKey);
    if (visible && (expanded[row.key] ?? row.depth < 2)) open.add(row.key);
    return visible;
  });
}

export function resolveSelection(rows: StructureRow[], assetId: string | undefined, path: string[]): StructureRow | undefined {
  for (let length = path.length; length > 0; length--) {
    const row = rows.find(item => item.key === structureKey(assetId ?? '', path.slice(0, length)));
    if (row) return row;
  }
  return rows.find(row => row.assetId === assetId && row.depth === 0) ?? rows[0];
}
