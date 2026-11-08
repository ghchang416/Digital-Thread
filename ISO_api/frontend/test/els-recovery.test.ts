import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { IDBFactory, IDBObjectStore } from 'fake-indexeddb';
import type { Catalog, NodeRef } from '../src/shared/schema/types';
import { initialWorkspace } from '../src/shared/draft/workspace';
import { readRecovery, resetRecovery, saveRecovery } from '../src/shared/draft/recovery';
import { openRecoveryDatabase } from '../src/shared/draft/recovery-database';
import { makeLocalFile } from '../src/features/cam/import';
import { emptyCamSession } from '../src/features/cam/types';
import { emptyNcSession, ncSignature } from '../src/features/files/model';
import { applyElsRecovery, readElsRecovery, restorePreviousRecovery } from '../src/features/els/recovery';
import type { ElsRecoveryContext } from '../src/features/els/recovery';
import { snapshotOf, validateWorkspaceSnapshot, workspaceFromCandidate } from '../src/features/els/workspace';
import type { ElsCandidate, ElsMetadata, ElsSelection } from '../src/features/els/contracts';

const fields = (names: string[]) => names.map(fieldName => ({ fieldName }));
const catalog = { schemaHash: '0'.repeat(64), rulesVersion: 'test', types: {
  DtAsset: { fields: fields(['dt_elements', 'schema_version', 'asset_global_id']) },
  DtProject: { fields: fields(['main_workplan']) }, Workplan: { fields: fields(['its_elements']) },
  MachiningWorkingstep: { fields: fields(['its_id', 'its_operation']) },
  FreeformOperation: { fields: fields(['its_tool', 'ref_dt_cutting_tool']) },
  DtCuttingTool13399: { fields: fields([]) },
} } as unknown as Catalog;
const profileHash = '1'.repeat(64);
const selection: ElsSelection = { partNo: 'P', partRevision: '01', opNo: '010', programNo: '100', programRevision: 'A', orderedRowIds: ['row'], excludedRows: [], orderReason: null };
const context = (): ElsRecoveryContext => ({ catalog, profileHash, signal: new AbortController().signal, isCurrent: () => true });
beforeEach(() => { globalThis.indexedDB = new IDBFactory(); });

async function fixture(mode: 'replace-project' | 'append-tools' = 'replace-project') {
  const base = initialWorkspace(catalog);
  const file = await makeLocalFile(new Blob(['T1 M6\nM30']), 'original.nc');
  base.files[file.fileId] = file;
  base.rawInputs.uncommitted = '-';
  base.extraFields.selected = ['description'];
  const fresh = mode === 'replace-project' ? initialWorkspace(catalog) : structuredClone(base);
  const draft = fresh.draft;
  draft.nodes['tool-root'] = { nodeId: 'tool-root', typeId: 'DtAsset', fields: { dt_elements: [{ $node: 'tool' }] } };
  draft.nodes.tool = { nodeId: 'tool', typeId: 'DtCuttingTool13399', fields: {} };
  draft.assets.push({ assetNodeId: 'tool-root', elementNodeId: 'tool', role: 'tool' });
  draft.manualTools = [{ assetNodeId: 'tool-root', toolTypeId: 'MillingCuttingTool' }];
  const metadata: ElsMetadata = {
    elsImports: [{ importEntryId: 'source', sourceSha256: '2'.repeat(64), sourceSchemaHash: '3'.repeat(64), profileHash, sourceName: 'synthetic.mdb', readerVersion: 'test', selection,
      sourceRows: [{ rowId: 'row', table: 'Operation_Machining', values: { Part_No: 'P', Part_Rev: '01', Op_No: '010', PGMNO: '100', REVNO: 'A', TOOLNO: '1', DESC: 'Synthetic step' } }] }],
    elsOrigins: [], elsWorkplans: [], elsToolLinks: [], elsReviews: [], elsFileLinks: [],
  };
  if (mode === 'replace-project') {
    const wp = (draft.nodes[draft.assets[0].elementNodeId].fields.main_workplan as NodeRef).$node;
    draft.nodes[wp].fields.its_elements = [{ $node: 'step' }];
    draft.nodes.step = { nodeId: 'step', typeId: 'MachiningWorkingstep', fields: { its_id: 'Synthetic step' } };
    metadata.elsWorkplans = [{ workplanNodeId: wp, importEntryId: 'source', steps: [{ kind: 'els', stepNodeId: 'step', sourceRowId: 'row' }] }];
    metadata.elsToolLinks = [{ workplanNodeId: wp, stepNodeId: 'step', assetNodeId: 'tool-root', toolTag: 'T1', sourceToolNo: '1' }];
    metadata.elsOrigins = [{ importEntryId: 'source', nodeId: 'step', fieldName: 'its_id', kind: 'source', sources: [{ rowId: 'row', column: 'DESC' }], appliedValue: 'Synthetic step', rule: 'desc', reason: 'Source description', sourceUnit: null, targetUnit: null }];
  }
  draft.revision = mode === 'replace-project' ? 0 : base.draft.revision + 1;
  const candidate: ElsCandidate = { request: { requestId: 'request', importId: 'import', baseDraftId: base.draft.draftId, baseRevision: base.draft.revision,
    expectedSequence: 1, mode, profileHash, selection, includePlaceholders: true }, draft, metadata,
    requiredCapabilities: ['els-import-v1'], recoveryFormatVersion: 2, purpose: 'authoring-review-only', machineReady: false, finalizable: false, persisted: false };
  return { base, candidate, file };
}

async function fileCount() {
  const db = await openRecoveryDatabase();
  return new Promise<number>((resolve, reject) => {
    const tx = db.transaction('files', 'readonly');
    const count = tx.objectStore('files').count();
    tx.oncomplete = () => { db.close(); resolve(count.result); };
    tx.onabort = () => { db.close(); reject(tx.error); };
  });
}

test('replacement preserves unsaved workspace, provenance and original Blob; old reader/writer fail closed', async () => {
  const { base, candidate, file } = await fixture();
  await saveRecovery(base, 0);
  base.rawInputs.latest = 'unfinished';
  base.extraFields.latest = ['extra'];
  const original = structuredClone(base);
  const applied = await applyElsRecovery(base, candidate, 1, 'request', context());
  assert.deepEqual(base, original);
  assert.equal(applied.formatVersion, 2);
  assert.equal(applied.sequence, 2);
  assert.deepEqual(applied.data.camImports, []);
  assert.deepEqual(applied.data.files, {});
  const recovered = await readElsRecovery(context());
  assert.deepEqual(recovered.active?.data, applied.data);
  assert.deepEqual(recovered.previous?.data, original);
  assert.equal(await recovered.previous!.data.files[file.fileId].blob.text(), 'T1 M6\nM30');
  assert.equal(await fileCount(), 1);
  await assert.rejects(readRecovery(catalog), /형식/);
  await assert.rejects(saveRecovery(base, 1), /다른 탭/);
  await assert.rejects(saveRecovery(base, 2), /새 형식/);
  await assert.rejects(saveRecovery(applied.data, 2), /ELS/);
});

test('restore swaps one previous slot, preserves unsaved ELS edits and increases sequence', async () => {
  const { base, candidate } = await fixture();
  await saveRecovery(base, 0);
  const applied = await applyElsRecovery(base, candidate, 1, 'request', context());
  applied.data.draft.nodes.step.fields.its_id = 'User edit';
  applied.data.draft.revision++;
  applied.data.rawInputs.number = '-';
  const restored = await restorePreviousRecovery(applied.data, 2, context());
  assert.equal(restored.sequence, 3);
  assert.equal(restored.formatVersion, 1);
  assert.deepEqual(restored.data, base);
  assert.deepEqual((await readRecovery(catalog))?.data, base);
  const swapped = await restorePreviousRecovery(restored.data, 3, context());
  assert.equal(swapped.sequence, 4);
  assert.equal(swapped.formatVersion, 2);
  assert.deepEqual(swapped.data, applied.data);
  assert.deepEqual((await readElsRecovery(context())).previous?.data, base);
});

test('append-tools preserves all current files, raw input and NC session data', async () => {
  const { base, candidate, file } = await fixture('append-tools');
  const wp = (base.draft.nodes[base.draft.assets[0].elementNodeId].fields.main_workplan as NodeRef).$node;
  base.ncSessions = { [wp]: { ...emptyNcSession(), manualReason: 'Existing reason', appliedSignature: 'existing-confirmation' } };
  base.camSessions = { [wp]: { ...emptyCamSession(), fileIds: [file.fileId], pasteText: 'Uncommitted original' } };
  const signature = ncSignature(base.draft, wp, base.ncSessions[wp]);
  await saveRecovery(base, 0);
  const record = await applyElsRecovery(base, candidate, 1, 'request', context());
  for (const key of ['files', 'rawInputs', 'extraFields', 'camSessions', 'camImports', 'ncSessions'] as const) assert.deepEqual(record.data[key], base[key]);
  for (const [id, node] of Object.entries(base.draft.nodes)) assert.deepEqual(record.data.draft.nodes[id], node);
  assert.equal(record.data.draft.draftId, base.draft.draftId);
  assert.equal(record.data.draft.revision, base.draft.revision + 1);
  assert.equal(ncSignature(record.data.draft, wp, record.data.ncSessions![wp]), signature);
  assert.equal((await readElsRecovery(context())).previous, null);
});

test('append accepts backend empty-default normalization without changing existing draft representation', async () => {
  const { base, candidate } = await fixture('append-tools');
  base.draft.nodes.oldRoot = { nodeId: 'oldRoot', typeId: 'DtAsset', fields: { dt_elements: [{ $node: 'oldTool' }] } };
  base.draft.nodes.oldTool = { nodeId: 'oldTool', typeId: 'DtCuttingTool13399', fields: {} };
  base.draft.assets.push({ assetNodeId: 'oldRoot', elementNodeId: 'oldTool', role: 'tool' });
  base.draft.manualTools = [{ assetNodeId: 'oldRoot', toolTypeId: 'MillingCuttingTool' }];
  Object.assign(candidate.draft.nodes, structuredClone(base.draft.nodes));
  candidate.draft.assets = [...base.draft.assets, candidate.draft.assets.at(-1)!];
  candidate.draft.manualTools = [{ ...base.draft.manualTools[0], legacyUnits: false }, ...candidate.draft.manualTools!];
  candidate.draft.ncReviews = []; candidate.draft.toolLinks = [];
  await saveRecovery(base, 0);
  const result = await applyElsRecovery(base, candidate, 1, 'request', context());
  assert.deepEqual(result.data.draft.manualTools![0], base.draft.manualTools[0]);
  assert.equal(result.data.draft.ncReviews, base.draft.ncReviews);
  assert.equal(result.data.draft.toolLinks, base.draft.toolLinks);
});

test('two concurrent applies with the same sequence commit only one replacement', async () => {
  const { base, candidate } = await fixture();
  await saveRecovery(base, 0);
  const results = await Promise.allSettled([
    applyElsRecovery(base, candidate, 1, 'request', context()),
    applyElsRecovery(base, candidate, 1, 'request', context()),
  ]);
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 1);
  const failure = results.find(r => r.status === 'rejected') as PromiseRejectedResult;
  assert.match(String(failure.reason), /STALE_SEQUENCE/);
  const slots = await readElsRecovery(context());
  assert.equal(slots.active?.sequence, 2);
  assert.deepEqual(slots.previous?.data, base);
  assert.equal(await fileCount(), 1);
});

test('second replacement retains only active/previous Blob union and stale restore preserves both', async () => {
  const { base, candidate } = await fixture();
  await saveRecovery(base, 0);
  const first = await applyElsRecovery(base, candidate, 1, 'request', context());
  const file = await makeLocalFile(new Blob(['second original']), 'second.nc');
  first.data.files[file.fileId] = file;
  const { candidate: second } = await fixture();
  Object.assign(second.request, { baseDraftId: first.data.draft.draftId, baseRevision: first.data.draft.revision, expectedSequence: 2 });
  const result = await applyElsRecovery(first.data, second, 2, 'request', context());
  assert.equal(await fileCount(), 1);
  assert.deepEqual((await readElsRecovery(context())).previous?.data, first.data);
  await assert.rejects(restorePreviousRecovery(result.data, 2, context()), /STALE_SEQUENCE/);
  const restored = await restorePreviousRecovery(result.data, 3, context());
  assert.deepEqual(restored.data, first.data);
  assert.equal(await restored.data.files[file.fileId].blob.text(), 'second original');
});

test('stale sequence, request, revision and replay cannot replace active or its files', async () => {
  const { base, candidate } = await fixture();
  await saveRecovery(base, 0);
  await assert.rejects(applyElsRecovery(base, candidate, 1, 'other-request', context()), /STALE_REQUEST/);
  const changed = structuredClone(base); changed.draft.revision++;
  await assert.rejects(applyElsRecovery(changed, candidate, 1, 'request', context()), /STALE_BASE/);
  await saveRecovery(base, 1);
  await assert.rejects(applyElsRecovery(base, candidate, 1, 'request', context()), /STALE_SEQUENCE/);
  assert.deepEqual((await readRecovery(catalog))?.data, base);
  assert.equal(await fileCount(), 1);
  candidate.request.expectedSequence = 2;
  const applied = await applyElsRecovery(base, candidate, 2, 'request', context());
  await assert.rejects(applyElsRecovery(applied.data, candidate, 3, 'request', context()), /STALE_BASE/);
});

test('cancellation and epoch change before commit never modify the active workspace', async () => {
  const { base, candidate } = await fixture();
  await saveRecovery(base, 0);
  const controller = new AbortController(); controller.abort(new Error('cancelled'));
  await assert.rejects(applyElsRecovery(base, candidate, 1, 'request', { ...context(), signal: controller.signal }), /cancelled/);
  let checks = 0;
  await assert.rejects(applyElsRecovery(base, candidate, 1, 'request', { ...context(), isCurrent: () => ++checks < 5 }), /STALE_OPERATION/);
  assert.deepEqual((await readRecovery(catalog))?.data, base);
  assert.equal((await readElsRecovery(context())).previous, null);
});

test('quota failure after Blob clear aborts both slot and file changes', async () => {
  const { base, candidate } = await fixture();
  await saveRecovery(base, 0);
  const put = IDBObjectStore.prototype.put;
  IDBObjectStore.prototype.put = function (...args: Parameters<IDBObjectStore['put']>) {
    if (this.name === 'workspace' && args[1] === 'previous') throw new DOMException('disk full', 'QuotaExceededError');
    return put.apply(this, args);
  };
  try { await assert.rejects(applyElsRecovery(base, candidate, 1, 'request', context()), /disk full/); }
  finally { IDBObjectStore.prototype.put = put; }
  assert.deepEqual((await readRecovery(catalog))?.data, base);
  assert.equal((await readElsRecovery(context())).previous, null);
  assert.equal(await fileCount(), 1);
});

test('file ID content conflicts and corrupted hashes are rejected without mutation', async () => {
  const { base, candidate, file } = await fixture();
  await saveRecovery(base, 0);
  const conflicting = structuredClone(base);
  const other = await makeLocalFile(new Blob(['DIFFERENT']), 'other.nc');
  conflicting.files[file.fileId] = { ...other, fileId: file.fileId };
  await assert.rejects(applyElsRecovery(conflicting, candidate, 1, 'request', context()), /FILE_ID_CONFLICT/);
  conflicting.files[file.fileId].sha256 = file.sha256;
  await assert.rejects(applyElsRecovery(conflicting, candidate, 1, 'request', context()), /FILE_HASH/);
  assert.deepEqual((await readRecovery(catalog))?.data, base);
});

test('replace before first save preserves unsaved files in previous; reset deletes both slots', async () => {
  const { base, candidate } = await fixture();
  candidate.request.expectedSequence = 0;
  const applied = await applyElsRecovery(base, candidate, 0, 'request', context());
  assert.equal(applied.sequence, 1);
  assert.deepEqual((await readElsRecovery(context())).previous?.data, base);
  const fresh = initialWorkspace(catalog);
  await resetRecovery(fresh, 1);
  const slots = await readElsRecovery(context());
  assert.equal(slots.active?.sequence, 2);
  assert.deepEqual(slots.active?.data, fresh);
  assert.equal(slots.previous, null);
  assert.equal(await fileCount(), 0);
  await assert.rejects(restorePreviousRecovery(fresh, 2, context()), /NO_PREVIOUS/);
});

test('unknown capability/profile and ELS metadata in v1 fail closed', async () => {
  const { base, candidate } = await fixture();
  const next = workspaceFromCandidate(base, candidate, 1, catalog, profileHash);
  const record = snapshotOf(next, 2);
  assert.throws(() => validateWorkspaceSnapshot(record, catalog, '9'.repeat(64)), /IMPORT_HEADER/);
  assert.throws(() => validateWorkspaceSnapshot({ ...record, requiredCapabilities: ['unknown'] } as never, catalog, profileHash), /CAPABILITY/);
  assert.throws(() => validateWorkspaceSnapshot({ formatVersion: 1, sequence: 2, savedAt: '', data: next }, catalog, profileHash), /ELS/);
});

for (const mutation of ['ownership', 'source-order', 'source-tool', 'origin', 'graph-cycle', 'review', 'inline-metadata', 'append-node', 'append-file'] as const) {
  test(`invalid candidate ${mutation} never touches active storage`, async () => {
    const { base, candidate } = await fixture(mutation.startsWith('append') ? 'append-tools' : 'replace-project');
    await saveRecovery(base, 0);
    const metadata = candidate.metadata, draft = candidate.draft;
    if (mutation === 'ownership') draft.manualWorkplans = [metadata.elsWorkplans[0].workplanNodeId];
    if (mutation === 'source-order') metadata.elsWorkplans[0].steps[0] = { kind: 'manual', stepNodeId: 'step', reason: 'fake' };
    if (mutation === 'source-tool') metadata.elsToolLinks[0].toolTag = 'T2';
    if (mutation === 'origin') metadata.elsOrigins[0].sources[0].column = 'MISSING';
    if (mutation === 'graph-cycle') draft.nodes.step.fields.its_operation = { $node: draft.projectAssetNodeId };
    if (mutation === 'review') metadata.elsReviews = [{ workplanNodeId: 'missing', snapshotHash: profileHash, profileHash, acknowledged: true }];
    if (mutation === 'inline-metadata') Object.assign(draft, { elsImports: metadata.elsImports });
    if (mutation === 'append-node') draft.nodes[draft.projectAssetNodeId].fields.asset_global_id = 'changed';
    if (mutation === 'append-file') draft.fileLinks = [{ assetNodeId: 'tool-root', fileId: 'fake', sha256: profileHash, purpose: 'NC', workplanNodeId: null }];
    await assert.rejects(applyElsRecovery(base, candidate, 1, 'request', context()));
    assert.deepEqual((await readRecovery(catalog))?.data, base);
    assert.equal((await readElsRecovery(context())).previous, null);
  });
}
