import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { IDBFactory } from 'fake-indexeddb';
import { applyCommand } from '../src/shared/draft/model';
import { assetReferenceUsers, pickerPolicy, referenceRecoveryError, referenceTargets } from '../src/shared/draft/references';
import { NodeEditor } from '../src/shared/schema/node-editor';
import type { Catalog, Draft, Field } from '../src/shared/schema/types';
import { readRecovery, saveRecovery } from '../src/shared/draft/recovery';
import type { WorkspaceData } from '../src/shared/draft/workspace';

const field: Field = { fieldName: 'configured_ref', label: '설정된 참조', declaredBy: 'Owner', xmlName: 'configured_ref', xmlKind: 'Element', namespace: null, kind: 'object', objectTypes: ['Reference'], enumTypes: [], scalarTypes: [], repeated: false, required: false, minOccurs: 0, maxOccurs: 1, managed: true, referencePolicyId: 'configured-policy' };
const catalog = { schemaVersion: 'v31', schemaHash: '0'.repeat(64), rulesVersion: 'test', referencePolicyHash: '1'.repeat(64), referencePolicies: [{ id: 'configured-policy', sourceType: 'Owner', fieldName: 'configured_ref', label: '설정된 참조', targetRole: 'material', targetType: 'CustomMaterial', editor: 'asset-picker' }], types: {
  Root: { label: '자산', fields: [{ fieldName: 'children' }] },
  Owner: { label: '소유 객체', xmlName: 'owner', fields: [field] },
  CustomMaterial: { label: '재료', fields: [{ fieldName: 'display_name' }, { fieldName: 'element_id' }] },
  Machine: { label: '머신', fields: [] },
} } as unknown as Catalog;

function fixture(): Draft {
  return { draftVersion: 1, schemaVersion: 'v31', schemaHash: catalog.schemaHash, rulesVersion: 'test', draftId: 'test', revision: 0, projectAssetNodeId: 'root', assets: [
    { assetNodeId: 'root', elementNodeId: 'owner', role: 'project' },
    { assetNodeId: 'steel-root', elementNodeId: 'steel', role: 'material' },
    { assetNodeId: 'al-root', elementNodeId: 'al', role: 'material' },
    { assetNodeId: 'mill-root', elementNodeId: 'mill', role: 'machine' },
  ], nodes: {
    root: { nodeId: 'root', typeId: 'Root', fields: { children: [{ $node: 'owner' }] } },
    owner: { nodeId: 'owner', typeId: 'Owner', fields: {} },
    'steel-root': { nodeId: 'steel-root', typeId: 'Root', fields: { children: [{ $node: 'steel' }] } },
    steel: { nodeId: 'steel', typeId: 'CustomMaterial', fields: { display_name: 'Steel', element_id: 'steel' } },
    'al-root': { nodeId: 'al-root', typeId: 'Root', fields: { children: [{ $node: 'al' }] } },
    al: { nodeId: 'al', typeId: 'CustomMaterial', fields: { display_name: 'Aluminium', element_id: 'al' } },
    'mill-root': { nodeId: 'mill-root', typeId: 'Root', fields: { children: [{ $node: 'mill' }] } },
    mill: { nodeId: 'mill', typeId: 'Machine', fields: {} },
  } };
}
const select = (draft: Draft, targetAssetNodeId?: string) => applyCommand(draft, { kind: 'reference', nodeId: 'owner', policyId: 'configured-policy', targetAssetNodeId, policyHash: catalog.referencePolicyHash! });

test('configured reference selection replaces and unlinks without XML fields or target mutation', () => {
  const old = fixture();
  let draft = select(old, 'steel-root');
  assert.equal(draft.referenceLinks?.length, 1);
  assert.equal(old.referenceLinks, undefined);
  assert.deepEqual(draft.nodes.owner.fields, {});
  draft = select(draft, 'al-root');
  assert.deepEqual(draft.referenceLinks, [{ sourceNodeId: 'owner', policyId: 'configured-policy', targetAssetNodeId: 'al-root' }]);
  assert.equal(referenceRecoveryError(draft, catalog), undefined);
  draft = select(draft);
  assert.deepEqual(draft.referenceLinks, []);
  assert.deepEqual(draft.nodes, old.nodes);
});

test('referenced asset deletion is blocked and owner deletion prunes links', () => {
  const draft = select(fixture(), 'steel-root');
  assert.equal(assetReferenceUsers(draft, 'steel-root').length, 1);
  assert.equal(applyCommand(draft, { kind: 'delete-asset', assetNodeId: 'steel-root' }), draft);
  const removedOwner = applyCommand(draft, { kind: 'set', nodeId: 'root', field: 'children' });
  assert.deepEqual(removedOwner.referenceLinks, []);
  assert.ok(removedOwner.nodes.steel);
  const unlinked = select(draft);
  assert.ok(!applyCommand(unlinked, { kind: 'delete-asset', assetNodeId: 'steel-root' }).nodes.steel);
});

test('picker uses catalog policies and types rather than machine/material field names', () => {
  const policy = pickerPolicy(catalog, field)!;
  assert.deepEqual(referenceTargets(fixture(), policy).map(a => a.assetNodeId), ['steel-root', 'al-root']);
  assert.equal(pickerPolicy(catalog, { ...field, referencePolicyId: 'unknown' }), undefined);
  const html = renderToStaticMarkup(createElement(NodeEditor, { draft: select(fixture(), 'steel-root'), catalog, nodeId: 'owner', dispatch: () => {}, navigate: () => {}, openAsset: () => {}, rawInputs: {}, setRaw: () => {}, extras: [], setExtras: () => {} }));
  assert.match(html, /aria-label="설정된 참조"/);
  assert.match(html, /Steel/);
  assert.match(html, /설정된 참조 삭제/);
  assert.match(html, /연결 자산 열기/);
  assert.doesNotMatch(html, /타입 선택/);
});

test('recovery rejects stale policy, missing target, duplicate or manual links without changing data', () => {
  const draft = select(fixture(), 'steel-root');
  assert.match(referenceRecoveryError({ ...draft, referencePolicyHash: 'stale' }, catalog)!, /정책/);
  assert.match(referenceRecoveryError(select(draft, 'missing'), catalog)!, /대상/);
  assert.match(referenceRecoveryError(select(draft, 'mill-root'), catalog)!, /대상/);
  assert.match(referenceRecoveryError({ ...draft, referenceLinks: [...draft.referenceLinks!, ...draft.referenceLinks!] }, catalog)!, /대상/);
  assert.equal(referenceRecoveryError(fixture(), catalog), undefined);
});

test('local reload preserves references and policy identity', async () => {
  globalThis.indexedDB = new IDBFactory();
  const data: WorkspaceData = { draft: select(fixture(), 'steel-root'), role: 'project', assetId: 'root', path: ['owner'], rawInputs: {}, extraFields: {}, camSessions: {}, camImports: [], files: {} };
  await saveRecovery(data, 0);
  assert.deepEqual((await readRecovery(catalog))?.data.draft.referenceLinks, data.draft.referenceLinks);
  assert.deepEqual((await readRecovery(catalog))?.data.draft.referencePolicyHash, catalog.referencePolicyHash);
});
