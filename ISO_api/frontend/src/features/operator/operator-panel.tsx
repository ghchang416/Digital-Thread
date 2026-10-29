import { ArrowDown, ArrowRight, ArrowUp, FileCode2, Plus, Upload, Wrench, Settings2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { useState } from 'react';
import type { Catalog, Draft } from '../../shared/schema/types';
import { isRef } from '../../shared/schema/types';
import type { Command } from '../../shared/draft/model';
import { nodeTitle } from '../../shared/draft/model';
import { buildStructure } from '../../shared/draft/structure';
import { ReferencePicker } from '../../shared/schema/reference-picker';

export function OperatorPanel({ draft, catalog, workplanId, dispatch, select, workflow, addWorkplan, openAsset, review, editor, applyMaterial }: {
  draft: Draft; catalog: Catalog; workplanId?: string; dispatch: (command: Command) => void;
  select: (nodeId: string) => void; workflow: (id: string, tab: 'cam' | 'completion' | 'nc' | 'detail' | 'manual') => void;
  addWorkplan: (parentId: string) => void; openAsset: (id: string) => void; review: () => void; editor?: ReactNode;
  applyMaterial: (nodeIds: string[], policyId: string, target?: string) => void;
}) {
  const project = draft.assets.find(a => a.role === 'project')!;
  const projectNode = draft.nodes[project.elementNodeId];
  const rows = buildStructure(draft, catalog, [project]).filter(row => draft.nodes[row.nodeId]?.typeId === 'Workplan');
  const selected = rows.find(row => row.nodeId === workplanId) ?? rows[0];
  const wp = selected && draft.nodes[selected.nodeId];
  const elements = wp && Array.isArray(wp.fields.its_elements) ? wp.fields.its_elements : [];
  const policy = catalog.referencePolicies?.find(p => p.sourceType === 'Workplan' && p.editor === 'asset-picker');
  const materialPolicy = catalog.referencePolicies?.find(p => p.sourceType === 'Workpiece' && p.editor === 'asset-picker');
  const [material, setMaterial] = useState('');
  const workpieces = [...new Set(elements.flatMap(ref => {
    if (!isRef(ref)) return [];
    const feature = draft.nodes[ref.$node]?.fields.its_feature;
    const piece = isRef(feature) ? draft.nodes[feature.$node]?.fields.its_workpiece : undefined;
    return isRef(piece) && draft.nodes[piece.$node]?.typeId === 'Workpiece' ? [piece.$node] : [];
  }))];
  return <section className="operator-panel">
    <div className="section-heading"><h1>프로젝트 구성</h1><button className="primary" onClick={review}><FileCode2 size={16} />전체 XML 검토</button></div>
    <label className="project-name">프로젝트 이름<input value={String(projectNode.fields.display_name ?? '')} onChange={e => dispatch({ kind: 'set', nodeId: projectNode.nodeId, field: 'display_name', value: e.target.value })} /></label>
    <div className="operator-workspace"><nav className="workplan-list" aria-label="워크플랜 선택">{rows.map(row => <button key={row.key} className={row.nodeId === wp?.nodeId ? 'selected' : ''} onClick={() => select(row.nodeId)}><span>{'› '.repeat(Math.max(0, row.path.filter(id => draft.nodes[id]?.typeId === 'Workplan').length - 1))}{nodeTitle(draft.nodes[row.nodeId], catalog)}</span><ArrowRight size={15} /></button>)}</nav>
    {wp && <section className="workplan-content"><div className="section-heading"><label>워크플랜 이름<input value={String(wp.fields.its_id ?? '')} onChange={e => dispatch({ kind: 'set', nodeId: wp.nodeId, field: 'its_id', value: e.target.value })} /></label><button className="secondary" onClick={() => addWorkplan(wp.nodeId)}><Plus size={16} />하위 워크플랜</button></div>
      {policy && <label className="machine-reference">사용 설비<ReferencePicker draft={draft} catalog={catalog} nodeId={wp.nodeId} policy={policy} openAsset={openAsset} onChange={targetAssetNodeId => dispatch({ kind: 'reference', nodeId: wp.nodeId, policyId: policy.id, targetAssetNodeId, policyHash: catalog.referencePolicyHash! })} /></label>}
      <div className="export-toolbar"><button className="secondary" onClick={() => workflow(wp.nodeId, 'cam')}><Upload size={16} />CAM 가져오기</button><button className="secondary" onClick={() => workflow(wp.nodeId, 'manual')}><Plus size={16} />직접 작성</button><button className="secondary" onClick={() => workflow(wp.nodeId, 'completion')}><Settings2 size={16} />누락값 보완</button><button className="secondary" onClick={() => workflow(wp.nodeId, 'nc')}><Wrench size={16} />NC·공구 연결</button><button className="text-button" onClick={() => workflow(wp.nodeId, 'detail')}><ArrowRight size={16} />상세 편집</button></div>
      <ol className="operator-steps">{elements.map((ref, index) => isRef(ref) && draft.nodes[ref.$node] ? <li key={ref.$node}><span className="row-number">{index + 1}</span><button className="text-button" onClick={() => draft.nodes[ref.$node].typeId === 'Workplan' ? select(ref.$node) : workflow(ref.$node, 'detail')}><span>{nodeTitle(draft.nodes[ref.$node], catalog)}<small className="type-name">{catalog.types[draft.nodes[ref.$node].typeId]?.label}</small></span><ArrowRight size={15} /></button><div className="row-actions"><button className="icon-button" aria-label={`${index + 1}번 위로`} title="위로" disabled={index === 0} onClick={() => dispatch({ kind: 'move', nodeId: wp.nodeId, field: 'its_elements', index, direction: -1 })}><ArrowUp size={16} /></button><button className="icon-button" aria-label={`${index + 1}번 아래로`} title="아래로" disabled={index === elements.length - 1} onClick={() => dispatch({ kind: 'move', nodeId: wp.nodeId, field: 'its_elements', index, direction: 1 })}><ArrowDown size={16} /></button></div></li> : null)}</ol>
      {!elements.length && <p className="empty">등록된 가공이 없습니다.</p>}
      {materialPolicy && workpieces.length > 0 && <details><summary>공작물 재료 연결 · {workpieces.length}개</summary><div className="material-batch"><label>현재 워크플랜 공작물에 적용할 재료<select value={material} onChange={e => setMaterial(e.target.value)}><option value="">연결 해제</option>{draft.assets.filter(a => a.role === materialPolicy.targetRole).map(a => <option key={a.assetNodeId} value={a.assetNodeId}>{nodeTitle(draft.nodes[a.elementNodeId], catalog)}</option>)}</select></label><button className="secondary" onClick={() => { if (confirm(`현재 워크플랜의 공작물 ${workpieces.length}개에 재료 연결을 ${material ? '적용' : '해제'}할까요? 다른 위치에서도 같은 공작물을 사용한다면 함께 반영됩니다.`)) applyMaterial(workpieces, materialPolicy.id, material || undefined); }}>공작물 {workpieces.length}개에 적용</button></div>{workpieces.map(id => <div className="workpiece-reference" key={id}><button className="text-button" onClick={() => workflow(id, 'detail')}>{nodeTitle(draft.nodes[id], catalog)}<ArrowRight size={15} /></button><ReferencePicker draft={draft} catalog={catalog} nodeId={id} policy={materialPolicy} openAsset={openAsset} onChange={targetAssetNodeId => dispatch({ kind: 'reference', nodeId: id, policyId: materialPolicy.id, targetAssetNodeId, policyHash: catalog.referencePolicyHash! })} /></div>)}</details>}
    </section>}</div>{editor}
  </section>;
}
