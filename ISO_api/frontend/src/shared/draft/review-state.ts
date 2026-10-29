import type { Draft, Preview } from '../schema/types';

export interface ReviewSnapshot { revision: number; assetId: string; result: Preview }

export function activeRawErrors(draft: Draft, rawInputs: Record<string, string>): string[] {
  return Object.keys(rawInputs).filter(key => !!draft.nodes[key.split(':')[0]]);
}

export function currentReview(draft: Draft, assetId: string | undefined, rawInputs: Record<string, string>, preview: ReviewSnapshot | null): Preview | null {
  if (activeRawErrors(draft, rawInputs).length || preview?.revision !== draft.revision || preview.assetId !== assetId) return null;
  return preview.result;
}
