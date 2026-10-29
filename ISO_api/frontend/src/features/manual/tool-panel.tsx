import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, Check, Pencil } from 'lucide-react';
import type { Catalog, Draft } from '../../shared/schema/types';
import { fetchToolProfile, prepareTool } from '../../shared/api/client';
import type { ManualResult } from '../../shared/api/client';
import { toolInputValues } from './model';

export function ManualToolPanel({ draft, catalog, assetId, disabled, onApply, onDetail }: {
  draft: Draft; catalog: Catalog; assetId?: string; disabled: boolean; onApply: (result: ManualResult, revision: number) => void; onDetail: () => void;
}) {
  const profile = useQuery({ queryKey: ['manual-tool-profile'], queryFn: fetchToolProfile, staleTime: Infinity });
  const definition = draft.manualTools?.find(t => t.assetNodeId === assetId);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(''); const [type, setType] = useState('');
  const [values, setValues] = useState<Record<string, { value: string; unit: string }>>({});
  const [sync, setSync] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  function begin(existing: boolean) {
    setEditing(existing); setError(''); setSync(false);
    const asset = draft.assets.find(a => a.assetNodeId === assetId);
    setName(existing && asset ? String(draft.nodes[asset.elementNodeId]?.fields.display_name ?? '') : '');
    setType(existing ? definition?.toolTypeId ?? '' : '');
    setValues(existing ? toolInputValues(draft, assetId) : {});
  }
  async function submit() {
    if (!profile.data || !type) return;
    controller.current = new AbortController(); const signal = controller.current.signal;
    setBusy(true); setError('');
    try {
      const fields = catalog.types[type]?.fields ?? [];
      const input: Record<string, { value: number; unit: string }> = {};
      for (const p of profile.data.properties.filter(p => fields.some(f => f.fieldName === p.field.split('.')[0]))) {
        const v = values[p.name];
        if (!v?.value.trim()) continue;
        if (!Number.isFinite(Number(v.value))) throw new Error(`${p.label}: 숫자를 확인해 주세요.`);
        input[p.name] = { value: Number(v.value), unit: v.unit || p.unit };
      }
      const result = await prepareTool({ draft, expectedRevision: draft.revision, profileHash: profile.data.hash, name, toolTypeId: type, values: input, synchronize: sync, assetNodeId: editing ? assetId : null }, signal);
      if (!signal.aborted) { onApply(result, draft.revision); setName(''); setType(''); setValues({}); setEditing(false); }
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : '공구 처리 실패'); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  return <section className="manual-panel" aria-label="13399 공구 직접 등록">
    <div className="section-heading"><h2>{editing ? '공구 제원 수정' : '공구 직접 등록'}</h2><div className="row-actions"><button className="secondary" disabled={busy} onClick={() => begin(false)}><Plus size={16} />새 공구</button>{definition && <button className="secondary" disabled={busy} onClick={() => begin(true)}><Pencil size={16} />선택 공구 수정</button>}{assetId && <button className="text-button" onClick={onDetail}>상세 편집</button>}</div></div>
    {profile.isPending && <p role="status">공구 입력 규칙 불러오는 중...</p>}
    {profile.isError && <p role="alert">{profile.error.message}<button onClick={() => profile.refetch()}>다시 시도</button></p>}
    {profile.data && <fieldset disabled={busy || disabled}>
      <div className="manual-form"><label>공구 이름<input aria-label="직접 등록 공구 이름" value={name} maxLength={200} onChange={e => setName(e.target.value)} /></label><label>공구 타입<select aria-label="직접 등록 공구 타입" value={type} onChange={e => setType(e.target.value)}><option value="">타입 선택</option>{profile.data.toolTypes.map(t => <option key={t.typeId} value={t.typeId}>{t.label}</option>)}</select></label>
      {type && profile.data.properties.filter(p => catalog.types[type]?.fields.some(f => f.fieldName === p.field.split('.')[0])).map(p => <label key={p.name}>{p.label}<div className="manual-number"><input aria-label={p.label} type="number" min={p.min} step={p.integer ? 1 : 'any'} value={values[p.name]?.value ?? ''} onChange={e => setValues(old => ({ ...old, [p.name]: { value: e.target.value, unit: old[p.name]?.unit || p.unit } }))} /><select aria-label={`${p.label} 단위`} value={values[p.name]?.unit || p.unit} onChange={e => setValues(old => ({ ...old, [p.name]: { value: old[p.name]?.value ?? '', unit: e.target.value } }))}>{p.unit === 'mm' ? <><option value="mm">mm</option><option value="in">inch</option></> : <option value={p.unit}>{p.unit === 'deg' ? 'degree' : '개'}</option>}</select></div></label>)}
      </div>
      {editing && <label className="checkbox-label"><input type="checkbox" checked={sync} onChange={e => setSync(e.target.checked)} />연결된 워킹스텝의 공통 공구 제원을 이 값으로 동기화합니다.</label>}
      <div className="manual-actions"><button className="primary" disabled={!name.trim() || !type} onClick={() => void submit()}><Check size={16} />{busy ? '처리 중' : editing ? '제원 적용' : '13399 공구 등록'}</button></div>
    </fieldset>}
    {error && <p className="error-text" role="alert">{error}</p>}
  </section>;
}
