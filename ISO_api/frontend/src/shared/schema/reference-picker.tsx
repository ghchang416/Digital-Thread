import { ArrowUpRight } from 'lucide-react';
import type { Catalog, Draft, ReferencePolicy } from './types';
import { nodeTitle } from '../draft/model';
import { referenceTargets } from '../draft/references';

interface Props {
  draft: Draft; catalog: Catalog; nodeId: string; policy: ReferencePolicy;
  onChange: (assetId?: string) => void; openAsset: (assetId: string) => void;
}

export function ReferencePicker({ draft, catalog, nodeId, policy, onChange, openAsset }: Props) {
  const targets = referenceTargets(draft, policy);
  const link = draft.referenceLinks?.find(item => item.sourceNodeId === nodeId && item.policyId === policy.id);
  const target = targets.find(asset => asset.assetNodeId === link?.targetAssetNodeId);
  const root = target && draft.nodes[target.assetNodeId];
  const element = target && draft.nodes[target.elementNodeId];
  return <div className="reference-picker">
    <div className="reference-selection">
      <select id={`field-${nodeId}-${policy.fieldName}-`} aria-label={policy.label} value={link?.targetAssetNodeId ?? ''} onChange={e => onChange(e.target.value || undefined)}>
        <option value="">연결 안 함</option>
        {link && !target && <option value={link.targetAssetNodeId}>연결 대상 확인 필요</option>}
        {targets.map(asset => <option key={asset.assetNodeId} value={asset.assetNodeId}>{nodeTitle(draft.nodes[asset.elementNodeId], catalog)} · {String(draft.nodes[asset.assetNodeId].fields.id ?? '자산 ID 미입력')} · {asset.assetNodeId.slice(0, 6)}</option>)}
      </select>
      {target && <button className="icon-button" title="연결 자산 열기" aria-label={`${policy.label} 연결 자산 열기`} onClick={() => openAsset(target.assetNodeId)}><ArrowUpRight size={17} /></button>}
    </div>
    {root && element ? <dl className="reference-identity"><div><dt>글로벌 ID</dt><dd>{String(root.fields.asset_global_id ?? '미입력')}</dd></div><div><dt>자산 / 요소 ID</dt><dd>{String(root.fields.id ?? '미입력')} / {String(element.fields.element_id ?? '미입력')}</dd></div></dl> : <small>{targets.length ? '미연결' : `${catalog.types[policy.targetType]?.label ?? policy.targetType} 자산 없음`}</small>}
  </div>;
}
