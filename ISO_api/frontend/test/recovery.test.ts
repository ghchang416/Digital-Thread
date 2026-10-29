import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { IDBFactory } from 'fake-indexeddb';
import { initialWorkspace } from '../src/shared/draft/workspace';
import { readRecovery, resetRecovery, saveRecovery } from '../src/shared/draft/recovery';
import { makeLocalFile } from '../src/features/cam/import';
import type { Catalog } from '../src/shared/schema/types';

const fields = (names: string[]) => names.map(fieldName => ({ fieldName }));
const catalog = { schemaHash: '0'.repeat(64), rulesVersion: 'test', types: {
  DtAsset: { fields: fields(['dt_elements', 'schema_version', 'asset_global_id']) },
  DtProject: { fields: fields(['main_workplan']) }, Workplan: { fields: fields(['its_elements']) },
} } as unknown as Catalog;
beforeEach(() => { globalThis.indexedDB = new IDBFactory(); });

async function storedFileCount(): Promise<number> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open('dt-project-creator', 1);
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const db = open.result;
      const tx = db.transaction('files', 'readonly');
      const count = tx.objectStore('files').count();
      tx.oncomplete = () => { db.close(); resolve(count.result); };
      tx.onabort = () => { db.close(); reject(tx.error); };
    };
  });
}

test('reset commits a fresh workspace and clears all originals including orphaned blobs', async () => {
  const old = initialWorkspace(catalog);
  const file = await makeLocalFile(new Blob(['T1 M6']), 'test.nc');
  old.files[file.fileId] = file;
  old.rawInputs['uncommitted:number:'] = '-';
  old.extraFields.test = ['description'];
  await saveRecovery(old, 0);
  const noFiles = { ...old, files: {} };
  await saveRecovery(noFiles, 1);
  assert.equal(await storedFileCount(), 1);
  const fresh = initialWorkspace(catalog);
  const record = await resetRecovery(fresh, 2);
  assert.equal(record.sequence, 3);
  assert.equal(await storedFileCount(), 0);
  const recovered = await readRecovery(catalog);
  assert.deepEqual(recovered?.data, fresh);
  assert.notEqual(recovered?.data.draft.draftId, old.draft.draftId);
  assert.deepEqual(recovered?.data.camSessions, {});
  assert.deepEqual(recovered?.data.camImports, []);
  assert.deepEqual(recovered?.data.rawInputs, {});
});

test('stale reset cannot delete another tab\'s edits or originals', async () => {
  const old = initialWorkspace(catalog);
  const file = await makeLocalFile(new Blob(['T2 M6']), 'test.nc');
  old.files[file.fileId] = file;
  await saveRecovery(old, 0);
  const latest = { ...old, extraFields: { latest: ['description'] } };
  await saveRecovery(latest, 1);
  await assert.rejects(resetRecovery(initialWorkspace(catalog), 1), /다른 탭/);
  assert.equal(await storedFileCount(), 1);
  assert.deepEqual((await readRecovery(catalog))?.data.extraFields, latest.extraFields);
});

test('old tabs cannot resurrect discarded data after reset; new draft remains writable', async () => {
  const old = initialWorkspace(catalog);
  await saveRecovery(old, 0);
  const fresh = initialWorkspace(catalog);
  await resetRecovery(fresh, 1);
  await assert.rejects(saveRecovery(old, 1), /다른 탭/);
  const edited = { ...fresh, extraFields: { new: ['description'] } };
  await saveRecovery(edited, 2);
  assert.deepEqual((await readRecovery(catalog))?.data, edited);
});

test('reset works before the first automatic save', async () => {
  const fresh = initialWorkspace(catalog);
  const record = await resetRecovery(fresh, 0);
  assert.equal(record.sequence, 1);
  assert.equal(await storedFileCount(), 0);
  assert.equal((await readRecovery(catalog))?.data.draft.draftId, fresh.draft.draftId);
});

test('completion provenance and pending settings survive recovery and edits', async () => {
  const data = initialWorkspace(catalog);
  const nodeId = data.draft.projectAssetNodeId;
  data.draft.completionEntries = [{ nodeId, fieldName: 'schema_version', value: 'v30', kind: 'default', rule: 'test', reason: 'Original baseline' }];
  data.completionSettings = { wp: { includePlaceholders: true, values: { maximum_depth_of_cut: '2.5' } } };
  await saveRecovery(data, 0);
  const recovered = await readRecovery(catalog);
  assert.deepEqual(recovered?.data.draft.completionEntries, data.draft.completionEntries);
  assert.equal(recovered?.data.draft.nodes[nodeId].fields.schema_version, 'v31');
  assert.deepEqual(recovered?.data.completionSettings, data.completionSettings);
});
