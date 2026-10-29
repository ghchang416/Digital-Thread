import { useEffect, useRef, useState } from 'react';
import { Download, FileCode2, ArrowRight, X } from 'lucide-react';
import type { WorkspaceData } from '../../shared/draft/workspace';
import { activeRawErrors } from '../../shared/draft/review-state';
import { reviewAsset } from '../../shared/api/client';
import { artifactFor, createZip, downloadBlob, exportCounts, exportDocuments, generateReview, isCurrent } from './model';
import type { ExportReview } from './model';

export function ExportPanel({ data, openIssue }: { data: WorkspaceData; openIssue: (id: string, field: string | null) => void }) {
  const [review, setReview] = useState<ExportReview | null>(null);
  const [busy, setBusy] = useState(false); const [packing, setPacking] = useState(false);
  const [progress, setProgress] = useState(0); const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  const latest = useRef(data); latest.current = data;
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; request.current?.abort(); }; }, []);
  const current = isCurrent(review, data) ? review : null;
  const counts = current ? exportCounts(current) : null;
  async function generate() {
    if (request.current) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setProgress(0); setError(''); setReview(null);
    try {
      const next = await generateReview(data, reviewAsset, controller.signal, setProgress);
      if (!isCurrent(next, latest.current)) throw new Error('입력이 변경되었습니다. 다시 생성해 주세요.');
      setReview(next);
    } catch (e) { if (mounted.current) setError(controller.signal.aborted ? '생성을 취소했습니다.' : e instanceof Error ? e.message : '생성 실패'); }
    finally { request.current = null; if (mounted.current) setBusy(false); }
  }
  async function download() {
    if (!current || packing) return;
    setPacking(true); setError('');
    try {
      const bytes = await createZip(current);
      if (!mounted.current || !isCurrent(current, latest.current)) throw new Error('입력이 변경되었습니다. 다시 생성해 주세요.');
      downloadBlob('project-xml-review.zip', new Blob([bytes as Uint8Array<ArrayBuffer>], { type: 'application/zip' }));
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : '다운로드 실패'); }
    finally { if (mounted.current) setPacking(false); }
  }
  return <section className="export-panel">
    <div className="section-heading"><div><h1>전체 XML 검토</h1><span className="type-name">자산 {data.draft.assets.length}개 · 검토용 · DB 저장 및 플랫폼 전송 없음</span></div><button className="primary" disabled={busy || activeRawErrors(data.draft, data.rawInputs).length > 0} onClick={generate}><FileCode2 size={17} />XML 생성·검증</button></div>
    {busy && <div className="export-toolbar" role="status"><span>{progress} / {data.draft.assets.length}개 생성 중</span><button className="secondary" onClick={() => request.current?.abort()}><X size={16} />취소</button></div>}
    {activeRawErrors(data.draft, data.rawInputs).length > 0 && <p className="error-text" role="alert">숫자 형식이 올바르지 않은 입력을 먼저 수정해 주세요.</p>}
    {error && <p className="error-text" role="alert">{error}</p>}
    {review && !current && <p className="source-note">입력이 변경되었습니다. XML을 다시 생성해 주세요.</p>}
    {current && counts && <>
      <div className="export-toolbar"><p role="status">생성 {counts.generated}/{counts.total} · 오류 {counts.errors} · 보완 이력 {counts.warnings} · 파일 저장 대기 {counts.pending}</p><button className="secondary" disabled={packing || counts.generated !== counts.total || !counts.total || counts.errors > 0} onClick={download}><Download size={16} />{packing ? '묶음 생성 중' : '검토 XML 묶음 다운로드'}</button><button className="text-button" onClick={() => downloadBlob('validation-report.json', new Blob([JSON.stringify(exportDocuments(current), null, 2)], { type: 'application/json' }))}><Download size={15} />검증 보고서</button></div>
      <p className="source-note">모델 기반 검사 결과입니다. 임시 보완값·파일 저장 ID 미확정 항목은 보고서에 포함되며, ISO 전체 적합성 또는 실제 가공 안전성을 보증하지 않습니다.</p>
      {current.workflowIssues.map((issue, index) => <button className="export-issue error-text" key={index} onClick={() => issue.nodeId && openIssue(issue.nodeId, issue.fieldName)}>{issue.message}<ArrowRight size={15} /></button>)}
      <div className="export-assets">{current.assets.map(row => <article key={row.asset.assetNodeId}>
        <div className="section-heading"><div><h2>{row.label}</h2><span className="type-name">{row.asset.role} · {artifactFor(row) ? row.filename : 'XML 생성 안 됨'}</span></div><button className="secondary" onClick={() => openIssue(row.asset.elementNodeId, null)}><ArrowRight size={16} />수정</button></div>
        {row.error && <p className="error-text">{row.error}</p>}
        {!row.linked && <p className="source-note">등록된 자산 연결 없음 · XML 묶음에는 포함됩니다.</p>}
        {row.result?.issues.map((issue, index) => <button className="export-issue error-text" key={index} onClick={() => openIssue(issue.nodeId ?? row.asset.elementNodeId, issue.fieldName)}><span>{issue.fieldName}: {issue.message}</span><ArrowRight size={15} /></button>)}
        {!!row.result?.pendingStorage?.length && <p className="source-note">파일 저장 전 · value 생략 · 검토용 XML</p>}
        {!!row.result?.warnings?.length && <details><summary>보완 이력 {row.result.warnings.length}개</summary>{row.result.warnings.map((issue, index) => <button className="export-issue" key={index} onClick={() => openIssue(issue.nodeId ?? row.asset.elementNodeId, issue.fieldName)}>{issue.message}<ArrowRight size={15} /></button>)}</details>}
        {artifactFor(row) && <details><summary>검토 XML</summary><pre>{artifactFor(row)!.xml}</pre><button className="secondary" onClick={() => downloadBlob(row.filename.split('/').at(-1)!, new Blob([artifactFor(row)!.xml], { type: 'application/xml' }))}><Download size={16} />XML 다운로드</button></details>}
      </article>)}</div>
    </>}
  </section>;
}
