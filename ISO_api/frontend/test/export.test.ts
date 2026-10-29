import assert from 'node:assert/strict';
import test from 'node:test';
import { unzipSync, strFromU8 } from 'fflate';
import { generateReview, createZip, exportCounts, isCurrent, workflowIssues } from '../src/features/export/model';
import { newWorkspace, defaultPreferences, createAsset, addWorkplan, validatePreferences } from '../src/features/operator/model';
import { applyCommand } from '../src/shared/draft/model';
import type { Catalog, Preview } from '../src/shared/schema/types';
const catalog = { schemaVersion: 'v31', schemaHash: 'h', rulesVersion: 'r' } as Catalog;
const response = (id: string): Preview => ({ valid: true, finalizable: false, issues: [], artifacts: [{ assetNodeId: id, xml: '<dt_asset />' }] });

test('all assets use one snapshot and safe unique archive names', async () => {
  const data = newWorkspace(catalog, defaultPreferences);
  data.draft = createAsset(data.draft, 'material');
  data.draft = createAsset(data.draft, 'machine');
  data.draft.nodes[data.draft.assets[1].elementNodeId].fields.display_name = '../../project.xml';
  const before = structuredClone(data.draft); const calls: string[] = [];
  const result = await generateReview(data, async (snapshot, id) => {
    assert.deepEqual(snapshot, before); calls.push(id); return response(id);
  }, new AbortController().signal, () => {});
  assert.equal(calls.length, 3); assert.equal(exportCounts(result).generated, 3);
  const entries = unzipSync(await createZip(result));
  assert.equal(Object.keys(entries).length, 5);
  assert.ok(!Object.keys(entries).some(name => name.includes('..')));
  const manifest = JSON.parse(strFromU8(entries['manifest.json']));
  assert.equal(manifest.total, 3); assert.equal(manifest.persisted, false); assert.equal(manifest.finalizable, false);
  assert.deepEqual(data.draft, before);
});
test('partial request failures remain visible and block complete ZIP', async () => {
  const data = newWorkspace(catalog, defaultPreferences); data.draft = createAsset(data.draft, 'material');
  let n = 0;
  const result = await generateReview(data, async (_, id) => { if (++n === 1) throw new Error('network failed'); return response(id); }, new AbortController().signal, () => {});
  assert.equal(result.assets.length, 2); assert.equal(exportCounts(result).generated, 1);
  assert.match(result.assets[0].error!, /network/);
  await assert.rejects(createZip(result));
});
test('workflow or validation errors block a bundle even when every XML exists', async () => {
  const data = newWorkspace(catalog, defaultPreferences);
  const result = await generateReview(data, async (_, id) => response(id), new AbortController().signal, () => {});
  const issue = { nodeId: null, fieldName: null, itemId: null, code: 'NC_CONFIRMATION_REQUIRED', message: 'Confirm NC again' };
  result.workflowIssues.push(issue);
  await assert.rejects(createZip(result), /NC/);
  result.workflowIssues = [];
  result.assets[0].result!.issues.push(issue);
  await assert.rejects(createZip(result), /검증/);
});
test('missing/wrong XML response cannot create a successful bundle', async () => {
  const data = newWorkspace(catalog, defaultPreferences);
  const result = await generateReview(data, async () => response('wrong'), new AbortController().signal, () => {});
  assert.equal(exportCounts(result).errors, 1); await assert.rejects(createZip(result));
});
test('edits, raw inputs and reset invalidate export; selection does not', async () => {
  const data = newWorkspace(catalog, defaultPreferences);
  const result = await generateReview(data, async (_, id) => response(id), new AbortController().signal, () => {});
  assert.ok(isCurrent(result, { ...data, screen: 'detail' }));
  assert.ok(!isCurrent(result, { ...data, rawInputs: { [`${data.draft.assets[0].elementNodeId}:x:`]: '-' } }));
  assert.ok(!isCurrent(result, { ...data, draft: { ...data.draft, revision: data.draft.revision + 1 } }));
  assert.ok(!isCurrent(result, newWorkspace(catalog, defaultPreferences)));
});
test('pending storage and placeholder warnings remain in downloaded report', async () => {
  const data = newWorkspace(catalog, defaultPreferences);
  const result = await generateReview(data, async (_, id) => ({ ...response(id), pendingStorage: [{ nodeId: id, fieldName: 'value', itemId: null, code: 'FILE_STORAGE_PENDING', message: 'pending' }], warnings: [{ nodeId: id, fieldName: 'depth', itemId: null, code: 'PLACEHOLDER', message: 'authoring only' }] }), new AbortController().signal, () => {});
  const entries = unzipSync(await createZip(result));
  const report = JSON.parse(strFromU8(entries['validation-report.json']));
  assert.equal(report.assets[0].pendingStorage.length, 1); assert.equal(report.assets[0].warnings.length, 1);
  assert.equal(report.isoConformanceCertified, false);
});
test('aborted generation does not start another request', async () => {
  const data = newWorkspace(catalog, defaultPreferences); data.draft = createAsset(data.draft, 'material');
  const controller = new AbortController(); let calls = 0;
  await assert.rejects(generateReview(data, async (_, id) => { calls++; controller.abort(); return response(id); }, controller.signal, () => {}));
  assert.equal(calls, 1);
});
test('new identity defaults never follow a project name edit', () => {
  const data = newWorkspace(catalog, { ...defaultPreferences, uriPrefix: 'https://factory.test/' });
  const root = data.draft.projectAssetNodeId;
  const original = data.draft.nodes[root].fields.asset_global_id;
  const draft = applyCommand(data.draft, { kind: 'set', nodeId: data.draft.assets[0].elementNodeId, field: 'display_name', value: 'changed' });
  const next = createAsset(draft, 'material');
  assert.equal(next.nodes[root].fields.asset_global_id, original);
  assert.equal(next.nodes[next.assets.at(-1)!.assetNodeId].fields.asset_global_id, original);
  assert.equal(data.draft.nodes[data.draft.assets[0].elementNodeId].fields.display_name, undefined);
});
test('workplan creation retains mixed execution order and existing fields', () => {
  const data = newWorkspace(catalog, defaultPreferences);
  const wp = Object.values(data.draft.nodes).find(n => n.typeId === 'Workplan')!;
  wp.fields.its_elements = [{ $node: 'existing' }]; wp.fields.custom = false;
  const draft = addWorkplan(data.draft, wp.nodeId);
  assert.equal((draft.nodes[wp.nodeId].fields.its_elements as any[])[0].$node, 'existing');
  assert.equal(draft.nodes[wp.nodeId].fields.custom, false);
  assert.equal((wp.fields.its_elements as any[]).length, 1);
});
test('settings reject invalid URIs and normalize a trailing slash', () => {
  assert.equal(validatePreferences({ ...defaultPreferences, uriPrefix: 'https://factory.test/kitech' }).uriPrefix, 'https://factory.test/kitech/');
  for (const uriPrefix of ['javascript:alert(1)', 'https://u:p@example.test/', 'https://example.test/?q=x', 'https://example.test/#x', 'https://example.test/a b']) assert.throws(() => validatePreferences({ ...defaultPreferences, uriPrefix }));
});
test('13399 T elements may share asset ID; duplicate full identity is rejected', () => {
  const data = newWorkspace(catalog, defaultPreferences);
  data.draft = createAsset(data.draft, 'material'); data.draft = createAsset(data.draft, 'material');
  const [a, b] = data.draft.assets.slice(1);
  data.draft.nodes[a.assetNodeId].fields.id = 'tools_wp'; data.draft.nodes[b.assetNodeId].fields.id = 'tools_wp';
  data.draft.nodes[a.elementNodeId].fields.element_id = 'T1'; data.draft.nodes[b.elementNodeId].fields.element_id = 'T2';
  assert.equal(workflowIssues(data).length, 0);
  data.draft.nodes[b.elementNodeId].fields.element_id = 'T1';
  assert.equal(workflowIssues(data)[0].code, 'DUPLICATE_ASSET_ID');
});
