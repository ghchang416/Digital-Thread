import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';

export interface Choice { id: string; title: string; detail: string }
export function SelectionDialog({ title, choices, onSelect, onClose }: {
  title: string; choices: Choice[]; onSelect: (id: string) => void; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState('');
  useEffect(() => {
    const focus = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    ref.current?.querySelector('input')?.focus();
    return () => { ref.current?.close(); focus?.focus(); };
  }, []);
  const filtered = choices.filter(item => `${item.title} ${item.detail}`.toLowerCase().includes(query.toLowerCase()));
  return <dialog ref={ref} onCancel={event => { event.preventDefault(); onClose(); }} aria-labelledby="dialog-title">
    <div className="dialog-heading"><h2 id="dialog-title">{title}</h2><button className="icon-button" aria-label="닫기" title="닫기" onClick={onClose}><X size={18} /></button></div>
    <label className="search"><Search size={16} /><input autoFocus aria-label="항목 검색" placeholder="항목 검색" value={query} onChange={e => setQuery(e.target.value)} /></label>
    <div className="choices">{filtered.map(item => <button key={item.id} className="choice" onClick={() => { onSelect(item.id); onClose(); }}><strong>{item.title}</strong><small>{item.detail}</small></button>)}{!filtered.length && <p className="empty">해당하는 항목이 없습니다.</p>}</div>
  </dialog>;
}
