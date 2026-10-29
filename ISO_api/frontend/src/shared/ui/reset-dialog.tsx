import { useEffect, useRef, useState } from 'react';
import { FilePlus2, X } from 'lucide-react';

export function ResetDialog({ assetCount, fileCount, onConfirm, onClose }: {
  assetCount: number; fileCount: number; onConfirm: () => Promise<void>; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const focus = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    cancelRef.current?.focus();
    return () => { dialog?.close(); if (focus?.isConnected) focus.focus(); };
  }, []);
  async function confirmReset() {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError('');
    try { await onConfirm(); }
    catch (e) { busyRef.current = false; setBusy(false); setError(e instanceof Error ? e.message : '초기화에 실패했습니다. 기존 내용을 유지합니다.'); }
  }
  return <dialog className="reset-dialog" ref={ref} aria-labelledby="reset-title" aria-describedby="reset-description" aria-busy={busy} onCancel={event => { event.preventDefault(); if (!busyRef.current) onClose(); }}>
    <div className="dialog-heading"><h2 id="reset-title">새 프로젝트를 시작할까요?</h2><button className="icon-button" disabled={busy} title="닫기" aria-label="닫기" onClick={onClose}><X size={18} /></button></div>
    <p id="reset-description">작성 중인 프로젝트, 자산 {assetCount}개와 로컬 원본 파일 {fileCount}개를 초기화합니다. CAM·NC 연결과 편집 내용도 삭제되며 되돌릴 수 없습니다.</p>
    <p className="muted">URI 접두사·기본 화면 설정, 컴퓨터의 원본 파일과 서버에 저장된 데이터는 유지합니다.</p>
    {error && <p role="alert" className="error-text">{error}</p>}
    {busy && <p role="status" className="muted">로컬 초안을 초기화하고 있습니다.</p>}
    <div className="dialog-actions"><button className="secondary" ref={cancelRef} disabled={busy} onClick={onClose}>계속 작성</button><button className="danger-button" disabled={busy} onClick={() => void confirmReset()}><FilePlus2 size={16} />{busy ? '초기화 중' : '초기화하고 시작'}</button></div>
  </dialog>;
}
