import { useEffect, useRef, useState } from 'react';
import { Check, RefreshCw, FileSearch, FolderOpen } from 'lucide-react';
import { analyzeNc, compileNcTools } from '../../shared/api/client';
import type { Draft } from '../../shared/schema/types';
import type { LocalFile } from '../cam/types';
import { directSteps, ncSignature } from './model';
import type { NcSession, ToolConflict } from './model';
import { ManualNcPanel } from '../manual/nc-panel';

interface Props {
  draft: Draft; workplanId: string; files: Record<string, LocalFile>; session: NcSession; hasRawErrors: boolean;
  onChange: (session: NcSession) => void; onApply: (draft: Draft, revision: number, session: NcSession) => void; openFiles: () => void;
}
const propertyLabels: Record<string, string> = { effective_cutting_diameter: '유효 절삭 지름', corner_radius: '날끝 반경', functional_length: '공구 기능 길이', overhang_length: '돌출 길이', number_of_teeth: '날 수' };
export function NcEditor({ draft, workplanId, files, session, hasRawErrors, onChange, onApply, openFiles }: Props) {
  const links = (draft.fileLinks ?? []).filter(link => link.workplanNodeId === workplanId && link.purpose === 'NC');
  const link = links.length === 1 ? links[0] : undefined;
  const file = link ? files[link.fileId] : undefined;
  const analysis = file && session.analysis?.sha256 === file.sha256 && session.analysis.fileId === file.fileId && session.analysis.encoding === session.encoding ? session.analysis : undefined;
  const steps = directSteps(draft, workplanId);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [conflicts, setConflicts] = useState<ToolConflict[]>([]); const [ack, setAck] = useState(false);
  const active = useRef(true); const controller = useRef<AbortController | null>(null);
  useEffect(() => { active.current = true; return () => { active.current = false; controller.current?.abort(); }; }, []);
  const current = !!session.appliedSignature && session.appliedSignature === ncSignature(draft, workplanId, session);
  function change(next: NcSession) { setAck(false); setError(''); onChange(next); }
  async function analyze() {
    if (!file) return;
    setBusy(true); setError(''); setConflicts([]); setAck(false); controller.current = new AbortController();
    try {
      const result = await analyzeNc(file, session.encoding, controller.current.signal);
      if (!active.current) return;
      if (result.sha256 !== file.sha256 || result.fileId !== file.fileId) throw new Error('NC 원본 해시가 일치하지 않습니다.');
      onChange({ ...session, analysis: result, resolutions: {}, assignments: result.supported && result.events.length === steps.length ? Object.fromEntries(steps.map((id, index) => [id, result.events[index].eventId])) : {} });
    } catch (e) { if (active.current) setError(e instanceof Error ? e.message : 'NC 분석 실패'); }
    finally { if (active.current) setBusy(false); }
  }
  async function apply() {
    if (!file || !link || !analysis) return;
    setBusy(true); setError(''); controller.current = new AbortController();
    try {
      const result = await compileNcTools({ fileId: file.fileId, encoding: session.encoding, draft, workplanNodeId: workplanId, fileAssetNodeId: link.assetNodeId,
        assignments: steps.map(stepNodeId => ({ stepNodeId, eventId: session.assignments[stepNodeId] })), resolutions: session.resolutions }, file, controller.current.signal);
      if (!active.current) return;
      setConflicts(result.conflicts);
      if (result.ready && result.draft) { onApply(result.draft, draft.revision, session); setAck(false); }
    } catch (e) { if (active.current) setError(e instanceof Error ? e.message : '공구 연결 실패'); }
    finally { if (active.current) setBusy(false); }
  }
  if (draft.manualWorkplans?.includes(workplanId)) return <ManualNcPanel draft={draft} workplanId={workplanId} files={files} session={session} hasRawErrors={hasRawErrors} onChange={onChange} onApply={onApply} openFiles={openFiles} />;
  return <section className="nc-editor" aria-label="NC와 공구 연결">
    <div className="section-heading"><div><h2>NC·공구 연결</h2><span className="type-name">{String(draft.nodes[workplanId]?.fields.its_id || '워크플랜')} · 워킹스텝 {steps.length}개</span></div><button className="secondary" onClick={openFiles}><FolderOpen size={16} />파일 자산</button></div>
    <div className={`binding-status ${current ? 'valid' : ''}`} role="status">{current ? '연결 확인 완료' : session.appliedSignature ? '입력 변경 · 연결 재확인 필요' : 'NC 연결 확인 전'}</div>
    {!file ? <p className="empty">이 워크플랜에 배정된 실행용 NC 파일이 없습니다.</p> : <fieldset disabled={busy} className="cam-inputs">
      <div className="nc-source"><div><strong>{file.name}</strong><small>로컬 원본 · {(file.size / 1024).toFixed(1)} KiB</small></div><label>인코딩<select aria-label="NC 인코딩" value={session.encoding} onChange={e => { setConflicts([]); change({ ...session, encoding: e.target.value as NcSession['encoding'], analysis: undefined, assignments: {}, resolutions: {} }); }}><option value="utf-8">UTF-8</option><option value="cp949">CP949</option></select></label><button className="secondary" onClick={() => void analyze()}><FileSearch size={16} />{busy ? '처리 중' : 'NC 분석'}</button></div>
      {analysis && <>
        {analysis.diagnostics.length > 0 && <ul className="cam-diagnostics">{analysis.diagnostics.map(text => <li key={text}>{text}</li>)}</ul>}
        <details className="nc-events"><summary>공구 교환 {analysis.events.length}회 · 서로 다른 T 번호 {new Set(analysis.events.map(event => event.toolTag)).size}개</summary><ol>{analysis.events.map((event, index) => <li key={event.eventId}><strong>{index + 1}. {event.toolTag}</strong><span>{event.lineStart}–{event.lineEnd}행</span><code>{event.source}</code></li>)}</ol></details>
        <div className="section-heading"><h3>워킹스텝별 NC 구간</h3><button className="text-button" disabled={!analysis.supported || steps.length !== analysis.events.length} onClick={() => change({ ...session, assignments: Object.fromEntries(steps.map((id, index) => [id, analysis.events[index].eventId])), resolutions: {} })}><RefreshCw size={15} />순서로 연결</button></div>
        <div className="nc-matches">{steps.map((id, index) => <div className="nc-match" key={id}><span className="row-number">{index + 1}</span><strong>{String(draft.nodes[id].fields.its_id || '식별자 미입력')}</strong><select aria-label={`워킹스텝 ${index + 1} NC 구간`} value={session.assignments[id] ?? ''} disabled={!analysis.supported} onChange={e => { setConflicts([]); change({ ...session, assignments: { ...session.assignments, [id]: e.target.value }, resolutions: {} }); }}><option value="">구간 선택</option>{analysis.events.map((event, index) => <option key={event.eventId} value={event.eventId}>{index + 1}. {event.toolTag} · {event.lineStart}–{event.lineEnd}행</option>)}</select></div>)}</div>
        {!steps.length && <p className="empty">직접 연결할 워킹스텝이 없습니다.</p>}
        {conflicts.length > 0 && <section className="tool-conflicts"><h3>동일 T 공구값 확인</h3>{conflicts.map(conflict => <label key={`${conflict.toolTag}:${conflict.property}`}>{conflict.toolTag} · {propertyLabels[conflict.property] ?? conflict.property}<select aria-label={`${conflict.toolTag} ${conflict.property} 적용 값`} value={session.resolutions[conflict.toolTag]?.[conflict.property] ?? ''} onChange={e => { const values = { ...session.resolutions[conflict.toolTag] }; if (e.target.value === '') delete values[conflict.property]; else values[conflict.property] = Number(e.target.value); change({ ...session, resolutions: { ...session.resolutions, [conflict.toolTag]: values } }); }}><option value="">사용할 값 선택</option>{[...new Set(conflict.choices.map(choice => choice.value))].map(value => <option key={value} value={value}>{value} · {conflict.choices.filter(choice => choice.value === value).map(choice => choice.label).join(', ')}</option>)}</select></label>)}</section>}
        <div className="cam-apply"><label className="checkbox-label"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />NC 순서와 동일 T 공구값을 확인했습니다.</label><button className="primary" disabled={!ack || hasRawErrors || !analysis.supported || !steps.length || steps.some(id => !session.assignments[id])} onClick={() => void apply()}><Check size={16} />공구 생성·연결 적용</button></div>
      </>}
    </fieldset>}
    {hasRawErrors && <p className="error-text">숫자 입력 오류를 먼저 수정해 주세요.</p>}
    {error && <p role="alert" className="error-text">{error}</p>}
    {busy && <p role="status">NC·공구 처리 중입니다.</p>}
  </section>;
}
