import assert from 'node:assert/strict';
import test from 'node:test';
import { applyCamImport, makeLocalFile } from '../src/features/cam/import';
import { emptyCamSession } from '../src/features/cam/types';
import type { CamCandidate, CamSession } from '../src/features/cam/types';
import { applyCommand } from '../src/shared/draft/model';
import { initialWorkspace, validateRecovery } from '../src/shared/draft/workspace';
import type { Catalog, NodeRef } from '../src/shared/schema/types';

const catalog = { schemaHash: '0'.repeat(64), rulesVersion: 'test', types: {
  DtAsset: { fields: [{ fieldName: 'dt_elements' }, { fieldName: 'schema_version' }, { fieldName: 'asset_global_id' }] },
  DtProject: { fields: [{ fieldName: 'main_workplan' }] },
  Workplan: { fields: [{ fieldName: 'its_elements' }, { fieldName: 'its_id' }] },
  MachiningWorkingstep: { fields: [{ fieldName: 'its_id' }] },
} } as unknown as Catalog;
function fixture() {
  const data = initialWorkspace(catalog);
  const project = data.draft.assets[0].elementNodeId;
  const wp = (data.draft.nodes[project].fields.main_workplan as NodeRef).$node;
  const candidate = (id: string): CamCandidate => ({ candidateId: id, fileId: 'file', sourceIndex: id === 'a' ? 0 : 1, title: id, rootNodeId: id,
    nodes: { [id]: { nodeId: id, typeId: 'MachiningWorkingstep', fields: { its_id: id } } }, origins: [], diagnostics: [], unmappedPaths: [], unmappedCount: 0, importable: true });
  const session: CamSession = { ...emptyCamSession(), acknowledged: true, selectedIds: ['b', 'a'], result: { requestId: 'request', camType: 'nx', workplanNodeId: wp,
    parserVersion: 'test', mappingHash: 'hash', mapping: {}, fileResults: [{ fileId: 'file', name: 'same.json', sha256: 'hash', operationCount: 2, error: null }],
    operations: [candidate('a'), candidate('b')], partial: false, persisted: false } };
  return { data, wp, session };
}

test('CAM applies explicit selection order, preserves mixed/manual elements and baseline', () => {
  const { data, wp, session } = fixture();
  data.draft = applyCommand(data.draft, { kind: 'attach', nodeId: wp, field: 'its_elements', typeId: 'Workplan', repeated: true });
  const existing = data.draft.nodes[wp].fields.its_elements as NodeRef[];
  session.names.b = 'Edited';
  const result = applyCamImport(data.draft, wp, session, []);
  assert.deepEqual(result.draft.nodes[wp].fields.its_elements, [...existing, { $node: 'b' }, { $node: 'a' }]);
  assert.equal(result.draft.nodes.b.fields.its_id, 'Edited');
  assert.equal(result.entry.candidates[0].nodes.b.fields.its_id, 'b');
  assert.equal(data.draft.nodes.b, undefined);
  result.draft.nodes.b.fields.its_id = 'Next edit';
  assert.equal(result.entry.candidates[0].nodes.b.fields.its_id, 'b');
});
test('CAM only selected operations append and existing sibling workplans stay untouched', () => {
  const { data, wp, session } = fixture(); session.selectedIds = ['a'];
  const next = applyCamImport(data.draft, wp, session, []);
  assert.equal(next.draft.nodes.b, undefined);
  assert.equal(next.draft.revision, data.draft.revision + 1);
  assert.equal(Object.keys(data.draft.nodes).length, 3);
});
test('CAM rejects wrong target, unacknowledged results, duplicate names and blank names atomically', () => {
  const { data, wp, session } = fixture(); const original = structuredClone(data.draft);
  assert.throws(() => applyCamImport(data.draft, 'missing', session, []));
  assert.throws(() => applyCamImport(data.draft, wp, { ...session, acknowledged: false }, []));
  assert.throws(() => applyCamImport(data.draft, wp, { ...session, names: { a: 'same', b: 'same' } }, []));
  assert.throws(() => applyCamImport(data.draft, wp, { ...session, names: { a: ' ' } }, []));
  assert.deepEqual(data.draft, original);
});
test('CAM cannot silently reapply a source or overwrite an edited imported operation', () => {
  const { data, wp, session } = fixture();
  const applied = applyCamImport(data.draft, wp, session, []);
  const edited = applyCommand(applied.draft, { kind: 'set', nodeId: 'a', field: 'its_id', value: 'Manual' });
  const reparsed = structuredClone(session); reparsed.names = { a: 'Fresh A', b: 'Fresh B' };
  assert.throws(() => applyCamImport(edited, wp, reparsed, [applied.entry]), /이미/);
  assert.equal(edited.nodes.a.fields.its_id, 'Manual');
});
test('local source identity hashes content independently of names', async () => {
  const first = await makeLocalFile(new Blob(['{"a":0}']), 'same.json');
  const second = await makeLocalFile(new Blob(['{"a":false}']), 'same.json');
  assert.notEqual(first.fileId, second.fileId); assert.notEqual(first.sha256, second.sha256);
  await assert.rejects(makeLocalFile(new Blob([]), 'empty.json'));
});
test('recovery preserves empty optional controls and invalid numeric input', () => {
  const { data } = fixture();
  data.extraFields.test = ['description']; data.rawInputs['test:number:'] = '-';
  validateRecovery({ formatVersion: 1, sequence: 1, savedAt: new Date().toISOString(), data }, catalog);
  assert.equal(data.rawInputs['test:number:'], '-');
});
test('recovery rejects incompatible versions, broken references and missing CAM originals', () => {
  const { data, wp, session } = fixture();
  const record = { formatVersion: 1 as const, sequence: 1, savedAt: '', data };
  assert.throws(() => validateRecovery(record, { ...catalog, rulesVersion: 'next' }));
  data.draft.nodes[wp].fields.its_elements = [{ $node: 'missing' }];
  assert.throws(() => validateRecovery(record, catalog));
  delete data.draft.nodes[wp].fields.its_elements;
  data.camSessions[wp] = { ...session, fileIds: ['missing'] };
  assert.throws(() => validateRecovery(record, catalog));
});
