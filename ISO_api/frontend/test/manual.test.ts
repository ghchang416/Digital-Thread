import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { IDBFactory } from 'fake-indexeddb';
import { initialWorkspace } from '../src/shared/draft/workspace';
import { applyCommand } from '../src/shared/draft/model';
import { readRecovery, saveRecovery } from '../src/shared/draft/recovery';
import { manualRecoveryError } from '../src/features/manual/model';
import { emptyNcSession, ncSignature } from '../src/features/files/model';
import { makeLocalFile } from '../src/features/cam/import';
import type { Catalog, NodeRef } from '../src/shared/schema/types';
import { manualNcBlockers, ncReasonChoices, toggleNcReason } from '../src/features/manual/nc-readiness';

const fields = (names: string[]) => names.map(fieldName => ({ fieldName }));
const catalog = { schemaHash: '0'.repeat(64), rulesVersion: 'test', types: {
  DtAsset: { fields: fields(['dt_elements', 'schema_version', 'asset_global_id']) },
  DtProject: { fields: fields(['main_workplan']) }, Workplan: { fields: fields(['its_elements']) },
  DtCuttingTool13399: { fields: [] }, MachiningWorkingstep: { fields: [] },
} } as unknown as Catalog;
beforeEach(() => { globalThis.indexedDB = new IDBFactory(); });
test('NC reason choices preserve custom text and require explicit acknowledgement', () => {
  let reason = toggleNcReason('직접 기록한 확인 근거', ncReasonChoices[0], true);
  assert.ok(reason.includes('직접 기록한 확인 근거'));
  assert.equal(toggleNcReason(reason, ncReasonChoices[0], true), reason);
  assert.equal(toggleNcReason(reason, ncReasonChoices[0], false), '직접 기록한 확인 근거');
  const { data, wp } = fixture();
  const session = { ...emptyNcSession(), manualReason: reason, manualRows: { step: { stepNodeId: 'step', toolTag: 'T1', lineStart: 1, lineEnd: 2 } } };
  const state = { profileReady: true, busy: false, rawErrors: false, acknowledged: false };
  assert.deepEqual(manualNcBlockers(data.draft, wp, session, state), ['마지막 확인 체크박스를 선택해 주세요.']);
  assert.deepEqual(manualNcBlockers(data.draft, wp, session, { ...state, acknowledged: true }), []);
  session.manualReason = '';
  assert.ok(manualNcBlockers(data.draft, wp, session, { ...state, acknowledged: true }).some(s => s.includes('사유')));
});
test('NC disabled reasons identify missing tool, invalid range and input errors', () => {
  const { data, wp } = fixture();
  const session = { ...emptyNcSession(), manualReason: '확인', manualRows: { step: { stepNodeId: 'step', toolTag: 'bad', lineStart: 4, lineEnd: 2 } } };
  data.draft.manualToolLinks = [];
  const errors = manualNcBlockers(data.draft, wp, session, { profileReady: false, busy: false, rawErrors: true, acknowledged: true });
  assert.ok(errors.some(s => s.includes('T 번호, 시작·끝 행, 공구 연결')));
  assert.ok(errors.some(s => s.includes('숫자 형식')));
  assert.ok(errors.some(s => s.includes('공구 입력 규칙')));
});
function fixture() {
  const data = initialWorkspace(catalog);
  const wp = (data.draft.nodes[data.draft.assets[0].elementNodeId].fields.main_workplan as NodeRef).$node;
  data.draft = applyCommand(data.draft, { kind: 'asset', role: 'tool', typeId: 'DtCuttingTool13399' });
  const aid = data.draft.assets.at(-1)!.assetNodeId;
  data.draft.nodes.step = { nodeId: 'step', typeId: 'MachiningWorkingstep', fields: {} };
  data.draft.nodes[wp].fields.its_elements = [{ $node: 'step' }];
  data.draft.manualTools = [{ assetNodeId: aid, toolTypeId: 'MillingCuttingTool' }];
  data.draft.manualWorkplans = [wp];
  data.draft.manualToolLinks = [{ assetNodeId: aid, workplanNodeId: wp, stepNodeId: 'step' }];
  return { data, wp, aid };
}
test('manual extension preserves legacy record version, blobs, raw values and pending NC fields', async () => {
  const { data, wp } = fixture();
  const file = await makeLocalFile(new Blob(['T1 M6']), 'manual.nc'); data.files[file.fileId] = file;
  data.rawInputs['step:unknown:'] = '-';
  data.ncSessions = { [wp]: { ...emptyNcSession(), manualReason: '원문 확인', manualRows: { step: { stepNodeId: 'step', toolTag: 'T1', lineStart: 1, lineEnd: 1 } } } };
  const before = structuredClone(data);
  await saveRecovery(data, 0);
  const restored = await readRecovery(catalog);
  assert.equal(restored?.formatVersion, 1);
  assert.deepEqual(restored?.data.draft, before.draft);
  assert.deepEqual(restored?.data.ncSessions, before.ncSessions);
  assert.equal(await restored?.data.files[file.fileId].blob.text(), 'T1 M6');
  assert.deepEqual(restored?.data.rawInputs, before.rawInputs);
});
test('manual linked tools cannot be deleted; removing step prunes only its manual link', () => {
  const { data, wp, aid } = fixture();
  assert.equal(applyCommand(data.draft, { kind: 'delete-asset', assetNodeId: aid }), data.draft);
  const removed = applyCommand(data.draft, { kind: 'remove-item', nodeId: wp, field: 'its_elements', index: 0 });
  assert.equal(removed.manualToolLinks?.length, 0);
  assert.equal(removed.manualTools?.length, 1);
  assert.equal(manualRecoveryError(removed), undefined);
  assert.equal(applyCommand(removed, { kind: 'delete-asset', assetNodeId: aid }).manualTools?.length, 0);
});
test('manual NC confirmation changes with assignments, reason and tool references', () => {
  const { data, wp } = fixture(); const session = emptyNcSession();
  const before = ncSignature(data.draft, wp, session);
  session.manualReason = 'changed'; assert.notEqual(ncSignature(data.draft, wp, session), before);
  delete session.manualReason;
  data.draft.manualToolLinks = []; assert.notEqual(ncSignature(data.draft, wp, session), before);
});
test('damaged manual references are rejected without mutating records', () => {
  const { data } = fixture(); data.draft.manualToolLinks![0].assetNodeId = 'missing';
  const before = structuredClone(data);
  assert.ok(manualRecoveryError(data.draft)); assert.deepEqual(data, before);
});
