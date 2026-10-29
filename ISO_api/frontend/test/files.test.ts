import assert from 'node:assert/strict';
import test from 'node:test';
import { addFileAsset, bindFile, directSteps, emptyNcSession, ncSignature } from '../src/features/files/model';
import { makeLocalFile } from '../src/features/cam/import';
import { applyCommand } from '../src/shared/draft/model';
import { initialWorkspace, validateRecovery } from '../src/shared/draft/workspace';
import type { Catalog, NodeRef } from '../src/shared/schema/types';

const fields = (names: string[]) => names.map(fieldName => ({ fieldName }));
const catalog = { schemaHash: '0'.repeat(64), rulesVersion: 'test', types: {
  DtAsset: { fields: fields(['dt_elements', 'schema_version', 'id', 'asset_kind', 'asset_global_id']) },
  DtProject: { fields: fields(['main_workplan']) }, Workplan: { fields: fields(['its_elements', 'its_id']) },
  DtFile: { fields: fields(['element_id', 'display_name', 'category', 'content_type', 'path']) },
} } as unknown as Catalog;
function fixture() {
  const data = initialWorkspace(catalog);
  const wp = (data.draft.nodes[data.draft.assets[0].elementNodeId].fields.main_workplan as NodeRef).$node;
  return { data, wp };
}
test('file registration creates dt_file without a fabricated GridFS id and preserves originals', async () => {
  const { data, wp } = fixture();
  const file = await makeLocalFile(new Blob(['T1 M6']), 'part.nc');
  const next = addFileAsset(data.draft, file, 'NC');
  const asset = next.assets.at(-1)!;
  assert.equal(next.nodes[asset.elementNodeId].typeId, 'DtFile');
  assert.equal(next.nodes[asset.elementNodeId].fields.value, undefined);
  assert.equal(next.fileLinks![0].sha256, file.sha256);
  assert.equal(data.draft.assets.length, 1);
  data.draft = bindFile(next, asset.assetNodeId, wp);
  data.files[file.fileId] = file;
  data.ncSessions = { [wp]: emptyNcSession() };
  validateRecovery({ formatVersion: 1, sequence: 1, savedAt: '', data }, catalog);
  delete data.files[file.fileId];
  assert.throws(() => validateRecovery({ formatVersion: 1, sequence: 1, savedAt: '', data }, catalog), /원본/);
});
test('one execution NC per workplan; many files across project; delete removes binding', async () => {
  const { data, wp } = fixture();
  const file = await makeLocalFile(new Blob(['T1 M6']), 'one.nc');
  let draft = addFileAsset(data.draft, file, 'NC');
  const first = draft.assets.at(-1)!.assetNodeId;
  draft = bindFile(draft, first, wp);
  draft = addFileAsset(draft, await makeLocalFile(new Blob(['T2 M6']), 'two.nc'), 'NC');
  const second = draft.assets.at(-1)!.assetNodeId;
  assert.throws(() => bindFile(draft, second, wp), /하나만/);
  assert.throws(() => bindFile(draft, second, 'missing'));
  draft = applyCommand(draft, { kind: 'delete-asset', assetNodeId: first });
  assert.equal(draft.fileLinks!.length, 1);
  assert.equal(bindFile(draft, second, wp).fileLinks![0].workplanNodeId, wp);
});
test('NC signatures track actual graph changes and direct step order, not revision-only updates', () => {
  const { data, wp } = fixture();
  data.draft.nodes.a = { nodeId: 'a', typeId: 'MachiningWorkingstep', fields: { its_id: 'A' } };
  data.draft.nodes.b = { nodeId: 'b', typeId: 'MachiningWorkingstep', fields: { its_id: 'B' } };
  data.draft.nodes.child = { nodeId: 'child', typeId: 'Workplan', fields: { its_elements: [{ $node: 'c' }] } };
  data.draft.nodes.c = { nodeId: 'c', typeId: 'MachiningWorkingstep', fields: {} };
  data.draft.nodes[wp].fields.its_elements = [{ $node: 'a' }, { $node: 'child' }, { $node: 'b' }];
  assert.deepEqual(directSteps(data.draft, wp), ['a', 'b']);
  const session = emptyNcSession(); const signature = ncSignature(data.draft, wp, session);
  data.draft.revision++;
  assert.equal(ncSignature(data.draft, wp, session), signature);
  data.draft.nodes.a.fields.its_id = 'Edited';
  assert.notEqual(ncSignature(data.draft, wp, session), signature);
  data.draft.nodes.a.fields.its_id = 'A';
  (data.draft.nodes[wp].fields.its_elements as NodeRef[]).reverse();
  assert.notEqual(ncSignature(data.draft, wp, session), signature);
});
test('a linked tool cannot be deleted while a workingstep still uses it', () => {
  const { data, wp } = fixture();
  data.draft = applyCommand(data.draft, { kind: 'asset', role: 'tool', typeId: 'DtCuttingTool13399' });
  const asset = data.draft.assets.at(-1)!;
  data.draft.nodes.step = { nodeId: 'step', typeId: 'MachiningWorkingstep', fields: {} };
  data.draft.toolLinks = [{ workplanNodeId: wp, toolTag: 'T1', assetNodeId: asset.assetNodeId, stepNodeIds: ['step'] }];
  assert.equal(applyCommand(data.draft, { kind: 'delete-asset', assetNodeId: asset.assetNodeId }), data.draft);
  data.draft.toolLinks[0].stepNodeIds = [];
  assert.equal(applyCommand(data.draft, { kind: 'delete-asset', assetNodeId: asset.assetNodeId }).assets.length, 1);
});
