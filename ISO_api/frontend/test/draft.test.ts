import assert from 'node:assert/strict';
import test from 'node:test';
import { initialDraft, applyCommand } from '../src/shared/draft/model';
import type { Catalog } from '../src/shared/schema/types';
const catalog = { schemaHash: '0'.repeat(64), rulesVersion: 'test' } as Catalog;

test('new asset global IDs start with an editable KITECH prefix without changing existing IDs', () => {
  let draft = initialDraft(catalog);
  const rootId = draft.projectAssetNodeId;
  const prefix = 'https://digital-thread.re/kitech/';
  assert.equal(draft.nodes[rootId].fields.asset_global_id, prefix);
  draft = applyCommand(draft, { kind: 'set', nodeId: rootId, field: 'asset_global_id', value: `${prefix}project_001` });
  for (const [role, typeId] of [['machine', 'DtMachineTool'], ['material', 'DtMaterial']] as const) {
    const next = applyCommand(draft, { kind: 'asset', role, typeId });
    const assetId = next.assets.at(-1)!.assetNodeId;
    assert.equal(next.nodes[assetId].fields.asset_global_id, prefix);
    assert.equal(next.nodes[rootId].fields.asset_global_id, `${prefix}project_001`);
    const edited = applyCommand(next, { kind: 'set', nodeId: assetId, field: 'asset_global_id', value: 'https://example.test/custom' });
    assert.equal(edited.nodes[assetId].fields.asset_global_id, 'https://example.test/custom');
    assert.equal(next.nodes[assetId].fields.asset_global_id, prefix);
    draft = edited;
  }
});

test('project and main workplan have stable separate IDs', () => {
  const draft = initialDraft(catalog);
  assert.equal(draft.assets.length, 1);
  assert.equal(Object.keys(draft.nodes).length, 3);
  assert.notEqual(draft.projectAssetNodeId, draft.assets[0].elementNodeId);
});
test('editing preserves false and zero and does not mutate the previous graph', () => {
  const draft = initialDraft(catalog); const id = draft.assets[0].elementNodeId;
  const next = applyCommand(draft, { kind: 'set', nodeId: id, field: 'test', value: false });
  assert.equal(next.nodes[id].fields.test, false);
  assert.equal(draft.nodes[id].fields.test, undefined);
  assert.equal(applyCommand(next, { kind: 'set', nodeId: id, field: 'test', value: 0 }).nodes[id].fields.test, 0);
});
test('repeated objects can be added, reordered and removed', () => {
  let draft = initialDraft(catalog); const id = draft.assets[0].elementNodeId;
  draft = applyCommand(draft, { kind: 'attach', nodeId: id, field: 'its_workpieces', typeId: 'Workpiece', repeated: true });
  draft = applyCommand(draft, { kind: 'attach', nodeId: id, field: 'its_workpieces', typeId: 'Workpiece', repeated: true });
  const items = draft.nodes[id].fields.its_workpieces as { $node: string }[];
  draft = applyCommand(draft, { kind: 'move', nodeId: id, field: 'its_workpieces', index: 1, direction: -1 });
  assert.deepEqual(draft.nodes[id].fields.its_workpieces, [items[1], items[0]]);
  draft = applyCommand(draft, { kind: 'remove-item', nodeId: id, field: 'its_workpieces', index: 0 });
  assert.equal(draft.nodes[items[1].$node], undefined);
  assert.ok(draft.nodes[items[0].$node]);
});
test('type replacement and asset deletion prune only unreachable nodes', () => {
  let draft = initialDraft(catalog);
  draft = applyCommand(draft, { kind: 'asset', role: 'machine', typeId: 'DtMachineTool' });
  const asset = draft.assets[1];
  draft = applyCommand(draft, { kind: 'attach', nodeId: asset.elementNodeId, field: 'machine_tool', typeId: 'MachineToolRequirements', repeated: false });
  const old = draft.nodes[asset.elementNodeId].fields.machine_tool as { $node: string };
  draft = applyCommand(draft, { kind: 'attach', nodeId: asset.elementNodeId, field: 'machine_tool', typeId: 'MachineToolSpecification', repeated: false });
  assert.equal(draft.nodes[old.$node], undefined);
  draft = applyCommand(draft, { kind: 'delete-asset', assetNodeId: asset.assetNodeId });
  assert.equal(Object.keys(draft.nodes).length, 3);
  assert.equal(applyCommand(draft, { kind: 'delete-asset', assetNodeId: draft.projectAssetNodeId }), draft);
});
