import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Plus, Pencil, Link2, Unlink, Trash2 } from 'lucide-react';
import type { Catalog, Draft } from '../../shared/schema/types';
import { isRef } from '../../shared/schema/types';
import type { Command } from '../../shared/draft/model';
import { nodeTitle } from '../../shared/draft/model';
import { fetchToolProfile, prepareManualStep } from '../../shared/api/client';
import type { ManualResult } from '../../shared/api/client';
import { directSteps } from '../files/model';

export function ManualStepPanel({ draft, catalog, workplanId, disabled, onApply, dispatch, onDetail, openTools, openNc, openCompletion }: {
  draft: Draft; catalog: Catalog; workplanId: string; disabled: boolean;
  onApply: (result: ManualResult, revision: number) => void; dispatch: (command: Command) => void; onDetail: (id: string) => void; openTools: () => void; openNc: () => void; openCompletion: () => void;
}) {
  const profile = useQuery({ queryKey: ['manual-tool-profile'], queryFn: fetchToolProfile, staleTime: Infinity });
  const [name, setName] = useState(''); const [operation, setOperation] = useState(''); const [tool, setTool] = useState('');
  const [selected, setSelected] = useState<Record<string, string>>({}); const [sync, setSync] = useState(false);
  const [adopt, setAdopt] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const tools = draft.assets.filter(a => draft.manualTools?.some(t => t.assetNodeId === a.assetNodeId));
  const steps = directSteps(draft, workplanId);
  const elements = draft.nodes[workplanId]?.fields.its_elements;
  async function run(action: 'add' | 'assign' | 'unassign', stepId?: string) {
    if (!profile.data) return;
    controller.current = new AbortController(); const signal = controller.current.signal;
    setBusy(true); setError('');
    try {
      const linked = draft.manualToolLinks?.find(l => l.stepNodeId === stepId)?.assetNodeId;
      const result = await prepareManualStep({ draft, expectedRevision: draft.revision, profileHash: profile.data.hash, action, workplanNodeId: workplanId, stepNodeId: stepId ?? null, assetNodeId: action === 'add' ? tool : action === 'assign' ? selected[stepId!] || linked || null : null, name, operationTypeId: operation || null, synchronize: sync, adoptExisting: adopt }, signal);
      if (!signal.aborted) { onApply(result, draft.revision); if (action === 'add') setName(''); setSync(false); }
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : '워킹스텝 처리 실패'); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  return <section className="manual-panel" aria-label="워킹스텝 직접 작성">
    <div className="section-heading"><h2>워킹스텝 직접 작성</h2><button className="secondary" onClick={openTools}><Plus size={16} />공구 등록</button></div>
    {!draft.manualWorkplans?.includes(workplanId) && draft.toolLinks?.some(l => l.workplanNodeId === workplanId && l.stepNodeIds.length) && <label className="checkbox-label"><input type="checkbox" checked={adopt} onChange={e => setAdopt(e.target.checked)} />기존 CAM 공구·ID·제원을 유지하고 수동 관리로 전환합니다. 기존 단위 없는 길이는 mm로 해석하며 NC를 다시 확인합니다.</label>}
    {profile.isError && <p role="alert">{profile.error.message}<button onClick={() => profile.refetch()}>다시 시도</button></p>}
    {profile.data && <fieldset disabled={busy || disabled}><div className="manual-form"><label>워킹스텝 이름<input aria-label="수동 워킹스텝 이름" value={name} maxLength={200} onChange={e => setName(e.target.value)} /></label><label>가공 타입<select aria-label="수동 가공 타입" value={operation} onChange={e => setOperation(e.target.value)}><option value="">타입 선택</option>{profile.data.operationTypes.map(t => <option key={t.typeId} value={t.typeId}>{t.label}</option>)}</select></label><label>사용 공구<select aria-label="새 워킹스텝 공구" value={tool} onChange={e => setTool(e.target.value)}><option value="">공구 선택</option>{tools.map(a => <option key={a.assetNodeId} value={a.assetNodeId}>{nodeTitle(draft.nodes[a.elementNodeId], catalog)}</option>)}</select></label></div><button className="primary" disabled={!name.trim() || !operation || !tool} onClick={() => void run('add')}><Plus size={16} />워킹스텝 추가</button></fieldset>}
    <div className="manual-step-list">{steps.map((id, index) => {
      const link = draft.manualToolLinks?.find(l => l.stepNodeId === id);
      const pos = Array.isArray(elements) ? elements.findIndex(r => isRef(r) && r.$node === id) : -1;
      return <div className="manual-step-row" key={id}><span className="row-number">{index + 1}</span><button className="text-button" onClick={() => onDetail(id)}><Pencil size={15} />{nodeTitle(draft.nodes[id], catalog)}</button><select aria-label={`${index + 1}번 사용 공구`} value={selected[id] ?? link?.assetNodeId ?? ''} onChange={e => setSelected(old => ({ ...old, [id]: e.target.value }))}><option value="">공구 선택</option>{tools.map(a => <option key={a.assetNodeId} value={a.assetNodeId}>{nodeTitle(draft.nodes[a.elementNodeId], catalog)}</option>)}</select><div className="row-actions"><button className="icon-button" disabled={busy || disabled || !(selected[id] || link)} title="공구 연결·동기화" aria-label={`${index + 1}번 공구 연결`} onClick={() => void run('assign', id)}><Link2 size={16} /></button><button className="icon-button" disabled={busy || !link} title="참조 해제" aria-label={`${index + 1}번 공구 해제`} onClick={() => void run('unassign', id)}><Unlink size={16} /></button><button className="icon-button" disabled={busy || pos <= 0} title="위로" aria-label={`${index + 1}번 위로 이동`} onClick={() => dispatch({ kind: 'move', nodeId: workplanId, field: 'its_elements', index: pos, direction: -1 })}><ArrowUp size={16} /></button><button className="icon-button" disabled={busy || !Array.isArray(elements) || pos >= elements.length - 1} title="아래로" aria-label={`${index + 1}번 아래로 이동`} onClick={() => dispatch({ kind: 'move', nodeId: workplanId, field: 'its_elements', index: pos, direction: 1 })}><ArrowDown size={16} /></button><button className="icon-button" disabled={busy} title="워킹스텝 삭제" aria-label={`${index + 1}번 워킹스텝 삭제`} onClick={() => { if (confirm('이 워킹스텝을 삭제할까요? 공구 자산은 유지됩니다.')) dispatch({ kind: 'remove-item', nodeId: workplanId, field: 'its_elements', index: pos }); }}><Trash2 size={16} /></button></div></div>;
    })}</div>
    {!!steps.length && <><label className="checkbox-label"><input type="checkbox" checked={sync} onChange={e => setSync(e.target.checked)} />공구 연결 시 기존 내부 공통 제원을 선택한 13399 값으로 바꿉니다.</label><div className="manual-actions"><button className="secondary" onClick={openCompletion}>누락값 보완</button><button className="primary" onClick={openNc}><Link2 size={16} />NC 구간·T 확인</button></div></>}
    {error && <p role="alert" className="error-text">{error}</p>}
  </section>;
}
