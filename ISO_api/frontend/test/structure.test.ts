import assert from 'node:assert/strict';
import test from 'node:test';
import { applyCommand, initialDraft } from '../src/shared/draft/model';
import { buildStructure, resolveSelection, visibleStructure } from '../src/shared/draft/structure';
import type { Catalog, NodeRef } from '../src/shared/schema/types';

const catalog = { schemaHash: '0'.repeat(64), rulesVersion: 'test', types: {
  DtProject: { label: '프로젝트', fields: [{ fieldName: 'main_workplan', label: '메인 워크플랜' }] },
  Workplan: { label: '워크플랜', fields: [{ fieldName: 'its_elements', label: '실행 요소' }] },
  MachiningWorkingstep: { label: '워킹스텝', fields: [] },
  DtMaterial: { label: '재료', fields: [] },
} } as unknown as Catalog;

function fixture() {
  let draft = initialDraft(catalog);
  const project = draft.assets[0].elementNodeId;
  const main = (draft.nodes[project].fields.main_workplan as NodeRef).$node;
  draft = applyCommand(draft, { kind: 'attach', nodeId: main, field: 'its_elements', typeId: 'Workplan', repeated: true });
  draft = applyCommand(draft, { kind: 'attach', nodeId: main, field: 'its_elements', typeId: 'MachiningWorkingstep', repeated: true });
  const [child, step] = draft.nodes[main].fields.its_elements as NodeRef[];
  return { draft, project, main, child: child.$node, step: step.$node };
}

test('outline preserves mixed workplan/step order, relation and ancestry', () => {
  const { draft, project, main, child, step } = fixture();
  const rows = buildStructure(draft, catalog, draft.assets);
  assert.deepEqual(rows.map(row => row.nodeId), [project, main, child, step]);
  assert.deepEqual(rows[2].path, [project, main, child]);
  assert.equal(rows[2].relation, '실행 요소 1');
  assert.equal(rows[3].position, 2);
  assert.equal(rows[3].siblingCount, 2);
  assert.equal(rows[0].childCount, 1);
});

test('rename and reorder update the outline without changing stable row identity', () => {
  let { draft, main, child } = fixture();
  const previous = buildStructure(draft, catalog, draft.assets).find(row => row.nodeId === child)!;
  draft = applyCommand(draft, { kind: 'set', nodeId: child, field: 'its_id', value: 'finish' });
  draft = applyCommand(draft, { kind: 'move', nodeId: main, field: 'its_elements', index: 0, direction: 1 });
  const current = buildStructure(draft, catalog, draft.assets).at(-1)!;
  assert.equal(current.key, previous.key);
  assert.equal(current.title, 'finish');
  assert.equal(current.relation, '실행 요소 2');
});

test('search reveals matching nodes with ancestors even when collapsed', () => {
  const { draft, step } = fixture();
  const rows = buildStructure(draft, catalog, draft.assets);
  const collapsed = Object.fromEntries(rows.map(row => [row.key, false]));
  assert.equal(visibleStructure(rows, collapsed, '').length, 1);
  const found = visibleStructure(rows, collapsed, '워킹스텝');
  assert.equal(found.length, 3);
  assert.equal(found.at(-1)?.nodeId, step);
  assert.deepEqual(visibleStructure(rows, {}, 'unmatched'), []);
});

test('removing a selected descendant resolves to the nearest surviving ancestor', () => {
  let { draft, main, child } = fixture();
  const selected = buildStructure(draft, catalog, draft.assets).find(row => row.nodeId === child)!;
  draft = applyCommand(draft, { kind: 'remove-item', nodeId: main, field: 'its_elements', index: 0 });
  const rows = buildStructure(draft, catalog, draft.assets);
  assert.equal(resolveSelection(rows, selected.assetId, selected.path)?.nodeId, main);
  assert.equal(resolveSelection(rows, 'removed-asset', selected.path)?.depth, 0);
  assert.equal(resolveSelection([], 'missing', []), undefined);
});

test('malformed cycles and dangling nodes cannot loop outline traversal', () => {
  const { draft, project, child } = fixture();
  draft.nodes[child].fields.its_elements = [{ $node: project }, { $node: 'missing' }];
  const rows = buildStructure(draft, catalog, draft.assets);
  assert.equal(rows.length, 4);
  assert.equal(rows.find(row => row.nodeId === child)?.childCount, 0);
});

test('category filtering isolates assets without editing semantic revision', () => {
  const { draft } = fixture();
  const next = applyCommand(draft, { kind: 'asset', role: 'material', typeId: 'DtMaterial' });
  const revision = next.revision;
  const rows = buildStructure(next, catalog, next.assets.filter(asset => asset.role === 'material'));
  assert.equal(rows.length, 1);
  assert.equal(rows[0].nodeId, next.assets[1].elementNodeId);
  assert.equal(next.revision, revision);
});
