import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, FileSearch, FolderOpen } from 'lucide-react';
import { analyzeNc, confirmManualNc, fetchToolProfile } from '../../shared/api/client';
import type { Draft, ManualAssignment } from '../../shared/schema/types';
import type { LocalFile } from '../cam/types';
import { directSteps, ncSignature } from '../files/model';
import type { NcSession } from '../files/model';

export function ManualNcPanel({ draft, workplanId, files, session, hasRawErrors, onChange, onApply, openFiles }: {
  draft: Draft; workplanId: string; files: Record<string, LocalFile>; session: NcSession; hasRawErrors: boolean;
  onChange: (s: NcSession) => void; onApply: (d: Draft, revision: number, s: NcSession) => void; openFiles: () => void;
}) {
  const profile = useQuery({ queryKey: ['manual-tool-profile'], queryFn: fetchToolProfile, staleTime: Infinity });
  const link = draft.fileLinks?.find(l => l.workplanNodeId === workplanId && l.purpose === 'NC');
  const file = link && files[link.fileId];
  const steps = directSteps(draft, workplanId);
  const [source, setSource] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [ack, setAck] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    let active = true; setSource(''); setError('');
    if (file) void file.blob.arrayBuffer().then(buffer => {
      const text = new TextDecoder(session.encoding === 'cp949' ? 'euc-kr' : 'utf-8', { fatal: true }).decode(buffer);
      if (active) setSource(text.split(/\r?\n/).map((line, i) => `${i + 1}  ${line}`).join('\n'));
    }).catch(() => { if (active) setError('NC 원문을 읽을 수 없습니다. 인코딩을 확인해 주세요.'); });
    return () => { active = false; };
  }, [file, session.encoding]);
  useEffect(() => setAck(false), [draft.revision, session.encoding, session.manualRows, session.manualReason]);
  const current = !!session.appliedSignature && session.appliedSignature === ncSignature(draft, workplanId, session);
  function change(next: NcSession) { setAck(false); onChange(next); }
  function row(id: string): ManualAssignment { return session.manualRows?.[id] ?? { stepNodeId: id, toolTag: '', lineStart: 0, lineEnd: 0 }; }
  async function analyze() {
    if (!file) return;
    controller.current = new AbortController(); const signal = controller.current.signal;
    setBusy(true); setError('');
    try {
      const analysis = await analyzeNc(file, session.encoding, signal);
      if (signal.aborted) return;
      if (analysis.sha256 !== file.sha256) throw new Error('NC 파일 해시가 다릅니다.');
      change({ ...session, analysis, manualRows: analysis.events.length === steps.length && !Object.keys(session.manualRows ?? {}).length ? Object.fromEntries(steps.map((id, i) => [id, { stepNodeId: id, toolTag: analysis.events[i].toolTag, lineStart: analysis.events[i].lineStart, lineEnd: analysis.events[i].lineEnd }])) : session.manualRows });
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : 'NC 분석 실패'); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  async function confirm() {
    if (!file || !profile.data) return;
    controller.current = new AbortController(); const signal = controller.current.signal;
    setBusy(true); setError('');
    try {
      const result = await confirmManualNc({ draft, expectedRevision: draft.revision, profileHash: profile.data.hash, workplanNodeId: workplanId, fileId: file.fileId, encoding: session.encoding, assignments: steps.map(row), reason: session.manualReason ?? '', acknowledged: ack }, file, signal);
      if (!signal.aborted) { onApply(result.draft, draft.revision, session); setAck(false); }
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : 'NC 수동 확인 실패'); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  return <section className="manual-panel" aria-label="NC 수동 확인">
    <div className="section-heading"><h2>NC 구간·T 수동 확인</h2><button className="secondary" onClick={openFiles}><FolderOpen size={16} />파일 자산</button></div>
    <p role="status" className={`binding-status ${current ? 'valid' : ''}`}>{current ? '수동 확인 완료 · NC 의미·가공 안전성 미검증' : '수동 확인 필요'}</p>
    {!file ? <p className="empty">워크플랜에 실행 NC 파일을 배정해 주세요.</p> : <fieldset disabled={busy || hasRawErrors}>
      <div className="nc-source"><strong>{file.name}</strong><label>인코딩<select aria-label="수동 NC 인코딩" value={session.encoding} onChange={e => change({ ...session, encoding: e.target.value as NcSession['encoding'], analysis: undefined })}><option value="utf-8">UTF-8</option><option value="cp949">CP949</option></select></label><button className="secondary" onClick={() => void analyze()}><FileSearch size={16} />NC 구간 후보 확인</button></div>
      <details className="manual-source"><summary>NC 원문 · 줄 번호</summary><pre>{source || '원문 읽는 중...'}</pre></details>
      {session.analysis?.sha256 === file.sha256 && session.analysis.encoding === session.encoding && <><ul className="cam-diagnostics">{session.analysis.diagnostics.map((d, i) => <li key={i}>{d}</li>)}</ul><details><summary>분석된 공구 교환 구간 {session.analysis.events.length}개</summary>{session.analysis.events.map(e => <p key={e.eventId}>{e.toolTag} · {e.lineStart}–{e.lineEnd}행 · {e.source}</p>)}</details></>}
      <div className="manual-nc-list">{steps.map((id, index) => {
        const value = row(id), binding = draft.manualToolLinks?.find(l => l.stepNodeId === id);
        const asset = draft.assets.find(a => a.assetNodeId === binding?.assetNodeId);
        return <div className="manual-nc-row" key={id}><div><strong>{index + 1}. {String(draft.nodes[id]?.fields.its_id || '이름 미입력')}</strong><small>{asset ? String(draft.nodes[asset.elementNodeId]?.fields.display_name || '공구') : '공구 연결 필요'}</small></div><label>T 번호<input aria-label={`${index + 1}번 T 번호`} value={value.toolTag} placeholder="T1" onChange={e => change({ ...session, manualRows: { ...session.manualRows, [id]: { ...value, toolTag: e.target.value } } })} /></label><label>시작 행<input type="number" min={1} step={1} aria-label={`${index + 1}번 시작 행`} value={value.lineStart || ''} onChange={e => change({ ...session, manualRows: { ...session.manualRows, [id]: { ...value, lineStart: Number(e.target.value) } } })} /></label><label>끝 행<input type="number" min={1} step={1} aria-label={`${index + 1}번 끝 행`} value={value.lineEnd || ''} onChange={e => change({ ...session, manualRows: { ...session.manualRows, [id]: { ...value, lineEnd: Number(e.target.value) } } })} /></label></div>;
      })}</div>
      <label className="manual-reason">확인 근거·사유<textarea aria-label="NC 수동 확인 사유" maxLength={1000} value={session.manualReason ?? ''} onChange={e => change({ ...session, manualReason: e.target.value })} /></label>
      <label className="checkbox-label"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />NC 원문과 작업 순서·T 번호·공구를 직접 확인했습니다. 자동 의미 검증은 아닙니다.</label>
      <div className="manual-actions"><button className="primary" disabled={!profile.data || !ack || !steps.length || !session.manualReason?.trim() || steps.some(id => !row(id).toolTag || !row(id).lineStart || !row(id).lineEnd || !draft.manualToolLinks?.some(l => l.stepNodeId === id))} onClick={() => void confirm()}><Check size={16} />{busy ? '처리 중' : 'NC 수동 확인 적용'}</button></div>
    </fieldset>}
    {(error || profile.isError) && <p className="error-text" role="alert">{error || profile.error?.message}</p>}
  </section>;
}
