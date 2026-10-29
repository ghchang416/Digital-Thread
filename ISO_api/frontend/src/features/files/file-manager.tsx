import { useEffect, useRef, useState } from 'react';
import { Download, FilePlus2, ArrowRight } from 'lucide-react';
import type { Draft, FileLink } from '../../shared/schema/types';
import type { LocalFile } from '../cam/types';
import { makeLocalFile } from '../cam/import';

interface Props {
  draft: Draft; files: Record<string, LocalFile>; selectedAssetId?: string;
  onAdd: (files: LocalFile[], purpose: FileLink['purpose']) => void;
  onBind: (assetId: string, workplanId: string | null) => void; onSelect: (assetId: string) => void;
}
export function FileManager({ draft, files, selectedAssetId, onAdd, onBind, onSelect }: Props) {
  const [purpose, setPurpose] = useState<FileLink['purpose']>('NC');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const workplans = Object.values(draft.nodes).filter(node => node.typeId === 'Workplan');
  async function upload(list: File[]) {
    setBusy(true); setError('');
    try {
      const added: LocalFile[] = [];
      for (const file of list) added.push(await makeLocalFile(file, file.name));
      if (active.current) onAdd(added, purpose);
    } catch (e) { if (active.current) setError(e instanceof Error ? e.message : '파일을 읽지 못했습니다.'); }
    finally { if (active.current) setBusy(false); }
  }
  return <section className="file-manager" aria-label="파일 자산 목록">
    <div className="file-toolbar"><label>파일 종류<select aria-label="등록할 파일 종류" value={purpose} disabled={busy} onChange={e => setPurpose(e.target.value as FileLink['purpose'])}><option value="NC">NC</option><option value="STEP">STEP</option><option value="OTHER">기타</option></select></label><label className="file-add secondary"><FilePlus2 size={16} />{busy ? '파일 읽는 중' : '파일 추가'}<input aria-label="DT 파일 추가" type="file" multiple disabled={busy} onChange={e => { const files = Array.from(e.target.files ?? []); e.target.value = ''; if (files.length) void upload(files); }} /></label><span className="type-name">파일당 최대 8 MiB · 원본 로컬 보관</span></div>
    {error && <p role="alert" className="error-text">{error}</p>}
    <div className="file-register">{(draft.fileLinks ?? []).map(link => {
      const file = files[link.fileId];
      return <div className={`registered-file ${link.assetNodeId === selectedAssetId ? 'selected-file' : ''}`} key={link.assetNodeId}>
        <div className="file-info"><strong>{file?.name ?? '원본 누락'}</strong><small>{link.purpose} · {file ? `${(file.size / 1024).toFixed(1)} KiB` : ''} · dt_file</small></div>
        <label>대상 워크플랜<select aria-label={`${file?.name} 대상 워크플랜`} value={link.workplanNodeId ?? ''} onChange={e => { setError(''); try { onBind(link.assetNodeId, e.target.value || null); } catch (e) { setError(e instanceof Error ? e.message : '파일 배정 실패'); } }}><option value="">{link.purpose === 'NC' ? '미배정' : '프로젝트 전체'}</option>{workplans.map(wp => <option key={wp.nodeId} value={wp.nodeId}>{String(wp.fields.its_id || '이름 없는 워크플랜')} · {wp.nodeId.slice(0, 6)}</option>)}</select></label>
        <div className="row-actions"><button className="icon-button" title="원본 다운로드" aria-label={`${file?.name} 원본 다운로드`} disabled={!file} onClick={() => { const url = URL.createObjectURL(file.blob); const a = document.createElement('a'); a.href = url; a.download = file.name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}><Download size={16} /></button><button className="icon-button" title="파일 속성 편집" aria-label={`${file?.name} 속성 편집`} onClick={() => onSelect(link.assetNodeId)}><ArrowRight size={16} /></button></div>
      </div>;
    })}</div>
    {!draft.fileLinks?.length && <p className="empty">등록된 파일 자산이 없습니다.</p>}
  </section>;
}
