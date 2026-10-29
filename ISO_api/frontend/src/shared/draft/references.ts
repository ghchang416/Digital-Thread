import type { Catalog, Draft, Field, ReferencePolicy } from '../schema/types';

export function pickerPolicy(catalog: Catalog, field: Field): ReferencePolicy | undefined {
  return catalog.referencePolicies?.find(policy => policy.id === field.referencePolicyId && policy.editor === 'asset-picker');
}

export function referenceTargets(draft: Draft, policy: ReferencePolicy) {
  return draft.assets.filter(asset => asset.role === policy.targetRole && draft.nodes[asset.elementNodeId]?.typeId === policy.targetType);
}

export function assetReferenceUsers(draft: Draft, assetId: string) {
  return (draft.referenceLinks ?? []).filter(link => link.targetAssetNodeId === assetId && draft.nodes[link.sourceNodeId]);
}

export function referenceRecoveryError(draft: Draft, catalog: Catalog): string | undefined {
  if (draft.referenceLinks !== undefined && (!Array.isArray(draft.referenceLinks) || draft.referenceLinks.length > 10000)) return '로컬 참조 연결 형식이 손상되었습니다.';
  if (!draft.referenceLinks?.length) return;
  if (!catalog.referencePolicyHash || draft.referencePolicyHash !== catalog.referencePolicyHash) return '참조 정책이 현재 서버와 다릅니다. 기존 초안은 보존했습니다.';
  const seen = new Set<string>();
  for (const link of draft.referenceLinks) {
    if (!link || typeof link.sourceNodeId !== 'string' || typeof link.policyId !== 'string' || typeof link.targetAssetNodeId !== 'string') return '로컬 참조 연결 형식이 손상되었습니다.';
    const source = draft.nodes[link.sourceNodeId];
    const field = source && catalog.types[source.typeId]?.fields.find(item => item.referencePolicyId === link.policyId);
    const policy = field && pickerPolicy(catalog, field);
    const key = JSON.stringify([link.sourceNodeId, link.policyId]);
    if (!policy || seen.has(key) || field!.fieldName in source.fields || !referenceTargets(draft, policy).some(asset => asset.assetNodeId === link.targetAssetNodeId)) return '로컬 참조 대상 또는 정책을 확인할 수 없습니다. 기존 초안은 보존했습니다.';
    seen.add(key);
  }
}
