import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Check, Download, FileJson, Plus, Trash2, Upload } from 'lucide-react';
import type { Catalog } from '../../shared/schema/types';
import { parseCam } from '../../shared/api/client';
import { makeLocalFile } from './import';
import type { CamSession, LocalFile } from './types';

interface Props {
  catalog: Catalog; workplanId: string; title: string; session: CamSession; files: Record<string, LocalFile>;
  appliedIds: Set<string>;
  onChange: (session: CamSession, files?: LocalFile[]) => void;
  onApply: () => void;
}
export function CamImportEditor({ catalog, workplanId, title, session, files, onChange, onApply, appliedIds }: Props) {
  const [mode, setMode] = useState<'file' | 'paste'>('file');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = useRef(true);
  const request = useRef<AbortController | null>(null);
  useEffect(() => { active.current = true; return () => { active.current = false; request.current?.abort(); }; }, []);
  const result = session.result;
  function changeInput(change: Partial<CamSession>, newFiles?: LocalFile[]) {
    setError(''); onChange({ ...session, ...change, result: undefined, selectedIds: [], names: {}, acknowledged: false }, newFiles);
  }
  async function addFiles(input: { blob: Blob; name: string }[], mapping = false) {
    setBusy(true); setError('');
    try {
      const added: LocalFile[] = [];
      for (const file of input) added.push(await makeLocalFile(file.blob, file.name));
      if (!active.current) return;
      const ids = mapping ? session.fileIds : session.camType === 'nx' ? added.map(file => file.fileId) : [...session.fileIds, ...added.map(file => file.fileId)];
      if (ids.length > (session.camType === 'nx' ? 1 : 50)) throw new Error('NX는 파일 1개, PowerMill은 최대 50개를 선택할 수 있습니다.');
      const combined = { ...files, ...Object.fromEntries(added.map(file => [file.fileId, file])) };
      const mappingId = mapping ? added[0]?.fileId : session.mappingFileId;
      if ([...ids, ...(mappingId ? [mappingId] : [])].reduce((total, id) => total + combined[id].size, 0) > 31 * 1024 * 1024) throw new Error('한 번에 가져오는 파일의 합계는 31 MiB 이하로 선택해 주세요.');
      changeInput({ fileIds: ids, mappingFileId: mappingId, ...(mode === 'paste' && !mapping ? { pasteText: '' } : {}) }, added);
    } catch (e) { if (active.current) setError(e instanceof Error ? e.message : '파일을 읽지 못했습니다.'); }
    finally { if (active.current) setBusy(false); }
  }
  function moveFile(index: number, delta: number) {
    const ids = [...session.fileIds]; [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]]; changeInput({ fileIds: ids });
  }
  function moveOperation(index: number, delta: number) {
    if (!result) return;
    const operations = [...result.operations]; [operations[index], operations[index + delta]] = [operations[index + delta], operations[index]];
    onChange({ ...session, result: { ...result, operations }, selectedIds: operations.filter(op => session.selectedIds.includes(op.candidateId)).map(op => op.candidateId) });
  }
  async function parse() {
    setBusy(true); setError('');
    request.current = new AbortController();
    const requestId = crypto.randomUUID();
    try {
      const response = await parseCam(catalog, workplanId, requestId, session, files, request.current.signal);
      if (!active.current) return;
      if (response.requestId !== requestId || response.workplanNodeId !== workplanId || response.camType !== session.camType) throw new Error('파싱 응답의 대상이 일치하지 않습니다.');
      for (const file of response.fileResults) if (file.sha256 && file.sha256 !== files[file.fileId]?.sha256) throw new Error('파싱한 원본 파일이 일치하지 않습니다.');
      onChange({ ...session, result: response, selectedIds: response.operations.filter(op => op.importable).map(op => op.candidateId), names: {}, acknowledged: false });
    } catch (e) { if (active.current) setError(e instanceof Error ? e.message : 'CAM 파싱에 실패했습니다.'); }
    finally { if (active.current) setBusy(false); }
  }
  function downloadFile(file: LocalFile) {
    const url = URL.createObjectURL(file.blob); const link = document.createElement('a'); link.href = url; link.download = file.name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="cam-editor" aria-label="CAM 가져오기">
    <div className="section-heading"><div><h2>CAM 가져오기</h2><span className="type-name">대상 워크플랜 · {title}</span></div></div>
    <details className="cam-source-section" open={!result}><summary>원본 파일 <span className="muted">{session.camType === 'nx' ? 'NX' : 'PowerMill'} · {session.fileIds.length}개</span></summary><fieldset disabled={busy} className="cam-inputs">
      <div className="form-row"><label htmlFor="cam-type">CAM 형식</label><select id="cam-type" value={session.camType} onChange={e => {
        if (session.fileIds.length && !confirm('형식을 변경하면 현재 가져오기 목록과 파싱 결과가 초기화됩니다. 이미 추가한 워킹스텝은 유지됩니다. 계속할까요?')) return;
        changeInput({ camType: e.target.value as CamSession['camType'], fileIds: [], mappingFileId: undefined });
      }}><option value="nx">NX · 한 파일에 여러 작업</option><option value="powermill">PowerMill · 파일당 작업 하나</option></select></div>
      <div className="form-row"><span className="field-label">CAM JSON</span><div className="cam-source">
        <div className="segmented" role="group" aria-label="CAM 입력 방식"><button type="button" aria-pressed={mode === 'file'} onClick={() => setMode('file')}><Upload size={15} />파일 업로드</button><button type="button" aria-pressed={mode === 'paste'} onClick={() => setMode('paste')}><FileJson size={15} />내용 붙여넣기</button></div>
        {mode === 'file' ? <label className="file-upload"><Upload size={22} /><strong>{session.camType === 'nx' ? 'NX JSON 선택' : 'PowerMill JSON 추가'}</strong><small>파일당 최대 8 MiB</small><input aria-label="CAM JSON 파일" type="file" accept=".json,application/json" multiple={session.camType === 'powermill'} onChange={e => { const selected = Array.from(e.target.files ?? []); e.target.value = ''; if (selected.length) void addFiles(selected.map(file => ({ blob: file, name: file.name }))); }} /></label> : <div className="paste-input"><input aria-label="붙여넣기 파일 이름" placeholder="파일 이름.json" value={session.pasteName} onChange={e => onChange({ ...session, pasteName: e.target.value })} /><textarea aria-label="CAM JSON 내용" spellCheck={false} placeholder="JSON" value={session.pasteText} onChange={e => onChange({ ...session, pasteText: e.target.value })} /><button className="secondary" disabled={!session.pasteText.trim()} onClick={() => void addFiles([{ blob: new Blob([session.pasteText], { type: 'application/json' }), name: session.pasteName.trim() || 'pasted-cam.json' }])}><Plus size={15} />파일 목록에 추가</button></div>}
        <ol className="cam-files">{session.fileIds.map((id, index) => {
          const file = files[id]; const status = result?.fileResults.find(item => item.fileId === id);
          return <li key={id}><span className="row-number">{index + 1}</span><div className="file-info"><strong>{file.name}</strong><small>{(file.size / 1024).toFixed(1)} KiB{status && (status.error ? ' · 파싱 실패' : ` · ${status.operationCount}개 작업`)}</small>{status?.error && <span className="error-text">{status.error}</span>}</div><div className="row-actions">
            <button className="icon-button" title="원본 다운로드" aria-label={`${file.name} 다운로드`} onClick={() => downloadFile(file)}><Download size={15} /></button>
            {session.camType === 'powermill' && <><button className="icon-button" title="위로" aria-label={`${file.name} 위로`} disabled={index === 0} onClick={() => moveFile(index, -1)}><ArrowUp size={15} /></button><button className="icon-button" title="아래로" aria-label={`${file.name} 아래로`} disabled={index === session.fileIds.length - 1} onClick={() => moveFile(index, 1)}><ArrowDown size={15} /></button></>}
            <button className="icon-button" title="목록에서 삭제" aria-label={`${file.name} 삭제`} onClick={() => changeInput({ fileIds: session.fileIds.filter(value => value !== id) })}><Trash2 size={15} /></button></div></li>;
        })}</ol>
      </div></div>
      <details className="mapping-options"><summary>매핑 설정 <span className="muted">{session.mappingFileId ? files[session.mappingFileId].name : '기본 매핑'}</span></summary><div className="mapping-controls"><label>사용자 매핑 JSON<input aria-label="사용자 매핑 JSON" type="file" accept=".json,application/json" onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void addFiles([{ blob: file, name: file.name }], true); }} /></label>{session.mappingFileId && <button className="text-button" onClick={() => changeInput({ mappingFileId: undefined })}>기본 매핑으로 변경</button>}</div></details>
      <div className="cam-toolbar"><span className="muted">{session.fileIds.length}개 파일</span><button className="primary" disabled={!session.fileIds.length} onClick={() => void parse()}><FileJson size={16} />{busy ? '처리 중…' : '파싱 실행'}</button></div>
    </fieldset></details>
    {busy && <p role="status" className="muted">파일 처리 중입니다.</p>}
    {error && <p role="alert" className="error-text">{error}</p>}
    {result && <section className="cam-results"><div className="section-heading"><h3>파싱 결과 <span className="muted">{result.operations.length}</span></h3><span className="type-name">파싱 원본 · 추가됨 {result.operations.filter(op => appliedIds.has(op.rootNodeId)).length}개</span></div>
      {result.partial && <p className="error-text">일부 파일을 파싱하지 못했습니다. 파일별 오류를 확인해 주세요.</p>}
      {!result.operations.length && <p className="empty">가져올 수 있는 작업이 없습니다.</p>}
      <fieldset disabled={busy} className="cam-inputs"><ol className="cam-operations">{result.operations.map((op, index) => <li key={op.candidateId}>
        <div className="operation-summary"><input type="checkbox" aria-label={`${op.title} 선택`} disabled={!op.importable || appliedIds.has(op.rootNodeId)} checked={session.selectedIds.includes(op.candidateId)} onChange={e => {
          const ids = new Set(session.selectedIds); if (e.target.checked) ids.add(op.candidateId); else ids.delete(op.candidateId);
          onChange({ ...session, selectedIds: result.operations.filter(item => ids.has(item.candidateId)).map(item => item.candidateId) });
        }} /><span className="row-number">{index + 1}</span><div className="operation-name"><label htmlFor={`name-${op.candidateId}`}>워킹스텝 식별자</label><input id={`name-${op.candidateId}`} disabled={appliedIds.has(op.rootNodeId)} value={session.names[op.candidateId] ?? String(op.nodes[op.rootNodeId].fields.its_id ?? '')} placeholder="식별자 입력" onChange={e => onChange({ ...session, names: { ...session.names, [op.candidateId]: e.target.value } })} /><small>{files[op.fileId]?.name} · 작업 {op.sourceIndex + 1}</small></div><div className="row-actions"><button className="icon-button" title="위로" aria-label={`작업 ${index + 1} 위로`} disabled={index === 0} onClick={() => moveOperation(index, -1)}><ArrowUp size={15} /></button><button className="icon-button" title="아래로" aria-label={`작업 ${index + 1} 아래로`} disabled={index === result.operations.length - 1} onClick={() => moveOperation(index, 1)}><ArrowDown size={15} /></button></div></div>
        {appliedIds.has(op.rootNodeId) && <span className="applied-note">워크플랜에 추가됨</span>}
        <details className="operation-details"><summary>적용 값 {op.origins.length}개 · 확인 필요 {op.diagnostics.length}개 · 미매핑 {op.unmappedCount}개</summary><dl className="parsed-values">{op.origins.map((origin, n) => <div key={n}><dt>{catalog.types[op.nodes[origin.nodeId]?.typeId]?.fields.find(field => field.fieldName === origin.fieldName)?.label ?? origin.fieldName}<small>{origin.sourcePath}</small></dt><dd>{String(origin.value)}</dd></div>)}</dl>{op.diagnostics.length > 0 && <ul className="cam-diagnostics">{op.diagnostics.map((item, n) => <li key={n}>{item.sourcePath || item.fieldName}: {item.message}</li>)}</ul>}{op.unmappedCount > 0 && <details><summary>미매핑 원본 항목</summary><ul className="unmapped-list">{op.unmappedPaths.map(item => <li key={item}>{item}</li>)}</ul></details>}</details>
      </li>)}</ol>
      {result.operations.length > 0 && <div className="cam-apply"><label className="checkbox-label"><input type="checkbox" checked={session.acknowledged} onChange={e => onChange({ ...session, acknowledged: e.target.checked })} />누락·미매핑 항목을 확인했습니다.</label><button className="primary" disabled={!session.acknowledged || !session.selectedIds.length} onClick={() => { setError(''); try { onApply(); } catch (e) { setError(e instanceof Error ? e.message : '추가하지 못했습니다.'); } }}><Check size={16} />선택한 {session.selectedIds.length}개 추가</button></div>}
      </fieldset>
    </section>}
  </section>;
}
