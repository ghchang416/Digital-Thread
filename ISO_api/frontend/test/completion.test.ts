import assert from 'node:assert/strict';
import { test } from 'node:test';
import { groupIssues, workplanSteps, formatValue } from '../src/features/completion/model';
import type { Draft, Issue } from '../src/shared/schema/types';
import type { StructureRow } from '../src/shared/draft/structure';

const draft = { nodes: {
  wp: { typeId: 'Workplan', fields: { its_id: 'Main', its_elements: [{ $node: 'a' }, { $node: 'b' }, { $node: 'nested' }] } },
  a: { typeId: 'MachiningWorkingstep', fields: { its_id: 'A' } },
  b: { typeId: 'MachiningWorkingstep', fields: { its_id: 'B' } },
  nested: { typeId: 'Workplan', fields: { its_id: 'Sub', its_elements: [{ $node: 'c' }] } },
  c: { typeId: 'MachiningWorkingstep', fields: { its_id: 'C' } },
} } as unknown as Draft;
const rows = [['wp'], ['wp', 'a'], ['wp', 'a', 'tech-a'], ['wp', 'b'], ['wp', 'b', 'tech-b'], ['wp', 'nested', 'c']].map(path => ({ nodeId: path.at(-1), path, typeLabel: 'Technology', relation: 'its_technology', assetId: 'root' })) as StructureRow[];
const issue = (nodeId: string, fieldName: string): Issue => ({ nodeId, fieldName, code: 'REQUIRED_FIELD', itemId: null, message: 'required' });

test('only direct machining steps belong to the selected workplan batch', () => {
  assert.deepEqual(workplanSteps(draft, 'wp'), ['a', 'b']);
  assert.deepEqual(workplanSteps(draft, 'nested'), ['c']);
});
test('repeated field errors retain workplan, step and object context', () => {
  const grouped = groupIssues([issue('tech-a', 'coolant'), issue('tech-b', 'coolant'), issue('a', 'its_secplane'), issue('c', 'its_feature')], rows, draft);
  assert.equal(grouped.length, 3);
  assert.equal(grouped[0].title, 'Main / A');
  assert.equal(grouped[0].issues.length, 2);
  assert.equal(grouped[1].title, 'Main / B');
  assert.equal(grouped[2].title, 'Main / Sub / C');
  assert.match(grouped[0].issues[0].context, /Technology/);
});
test('provenance formatting preserves zero and false and resolves object titles', () => {
  assert.equal(formatValue(0, draft), '0');
  assert.equal(formatValue(false, draft), 'false');
  assert.equal(formatValue({ $node: 'a' }, draft), 'A');
  assert.equal(formatValue([{ itemId: 'x', value: 0 }, { itemId: 'z', value: 50 }], draft), '0, 50');
});

test('file diagnostics use the file name instead of a project fallback', () => {
  const fileDraft = { ...draft, assets: [{ assetNodeId: 'file-root', elementNodeId: 'file', role: 'file' }], nodes: { ...draft.nodes, file: { nodeId: 'file', typeId: 'DtFile', fields: { path: 'part.nc' } } } } as Draft;
  const fileRows = [{ nodeId: 'file', path: ['file'], assetId: 'file-root', relation: '자산', typeLabel: '파일', title: 'part.nc' }] as StructureRow[];
  assert.equal(groupIssues([issue('file', 'content_type')], fileRows, fileDraft)[0].title, 'part.nc');
});
