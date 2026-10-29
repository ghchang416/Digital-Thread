import assert from 'node:assert/strict';
import test from 'node:test';
import { initialDraft } from '../src/shared/draft/model';
import { activeRawErrors, currentReview } from '../src/shared/draft/review-state';
import type { Catalog, Preview } from '../src/shared/schema/types';

const draft = initialDraft({ schemaHash: '0'.repeat(64), rulesVersion: 'test' } as Catalog);
const assetId = draft.projectAssetNodeId;
const result = { valid: true, finalizable: false, issues: [], artifacts: [] } as Preview;
const preview = { revision: draft.revision, assetId, result };

test('preview requires the current revision and asset', () => {
  assert.equal(currentReview(draft, assetId, {}, preview), result);
  assert.equal(currentReview({ ...draft, revision: draft.revision + 1 }, assetId, {}, preview), null);
  assert.equal(currentReview(draft, 'another-asset', {}, preview), null);
  assert.equal(currentReview(draft, assetId, {}, null), null);
});

test('uncommitted invalid numeric input hides an otherwise current preview', () => {
  const inputs = { [`${assetId}:number:`]: '-' };
  assert.equal(activeRawErrors(draft, inputs).length, 1);
  assert.equal(currentReview(draft, assetId, inputs, preview), null);
});

test('raw input for removed nodes cannot block the remaining draft', () => {
  const inputs = { 'removed-node:number:': '-' };
  assert.deepEqual(activeRawErrors(draft, inputs), []);
  assert.equal(currentReview(draft, assetId, inputs, preview), result);
});
