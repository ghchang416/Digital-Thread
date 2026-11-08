import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { IDBFactory } from 'fake-indexeddb';
import type { Catalog, Draft } from '../src/shared/schema/types';
import type { ElsCandidate } from '../src/features/els/contracts';
import { initialWorkspace } from '../src/shared/draft/workspace';
import { saveRecovery } from '../src/shared/draft/recovery';
import { applyElsRecovery, readElsRecovery, restorePreviousRecovery } from '../src/features/els/recovery';
import { makeLocalFile } from '../src/features/cam/import';

test('actual synthetic backend prepare/confirm payload survives local apply, read and restore', {
  skip: !process.env.ELS_RECOVERY_FIXTURE && 'Generate export_els_recovery_fixture.py output and set ELS_RECOVERY_FIXTURE',
}, async () => {
  const fixture = JSON.parse(await readFile(process.env.ELS_RECOVERY_FIXTURE!, 'utf8')) as {
    catalog: Catalog; profileHash: string; nc: string; base: Draft; replacement: ElsCandidate; append: ElsCandidate;
  };
  for (const mode of ['replacement', 'append'] as const) {
    globalThis.indexedDB = new IDBFactory();
    const data = initialWorkspace(fixture.catalog);
    data.draft = fixture.base;
    data.assetId = fixture.base.projectAssetNodeId;
    const file = await makeLocalFile(new Blob([fixture.nc]), 'synthetic.nc');
    file.fileId = fixture.base.fileLinks![0].fileId;
    data.files[file.fileId] = file;
    await saveRecovery(data, 0);
    const context = { catalog: fixture.catalog, profileHash: fixture.profileHash, signal: new AbortController().signal, isCurrent: () => true };
    const candidate = fixture[mode];
    const record = await applyElsRecovery(data, candidate, 1, candidate.request.requestId, context);
    assert.deepEqual(record.data.elsMetadata, candidate.metadata);
    assert.deepEqual((await readElsRecovery(context)).active?.data, record.data);
    if (mode === 'replacement') {
      assert.ok(record.data.elsMetadata.elsReviews.length);
      assert.ok(record.data.elsMetadata.elsFileLinks.length);
      assert.deepEqual((await restorePreviousRecovery(record.data, 2, context)).data, data);
    } else assert.deepEqual(record.data.files, data.files);
  }
});
