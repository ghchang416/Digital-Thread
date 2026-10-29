import { useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, KeyboardEvent } from 'react';
import { ChevronDown, ChevronRight, ChevronsDownUp, Crosshair, FileBox, FolderTree, Search, X } from 'lucide-react';
import { structureKey, visibleStructure } from '../draft/structure';
import type { StructureRow } from '../draft/structure';

interface Props { rows: StructureRow[]; selectedKey?: string; onSelect: (row: StructureRow) => void }

export function StructureTree({ rows, selectedKey, onSelect }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState('');
  const [focusedKey, setFocusedKey] = useState<string>();
  const refs = useRef(new Map<string, HTMLDivElement>());
  const selected = rows.find(row => row.key === selectedKey);
  const previousChildren = useRef({ key: selectedKey, count: selected?.childCount ?? 0 });
  const visible = useMemo(() => visibleStructure(rows, expanded, query), [rows, expanded, query]);
  const tabKey = visible.find(row => row.key === focusedKey)?.key ?? visible.find(row => row.key === selectedKey)?.key ?? visible[0]?.key;

  useEffect(() => {
    if (!selectedKey) return;
    const [asset, ...path] = JSON.parse(selectedKey) as string[];
    setExpanded(old => {
      const next = { ...old };
      for (let i = 1; i < path.length; i++) next[structureKey(asset, path.slice(0, i))] = true;
      return next;
    });
    setFocusedKey(selectedKey);
    setQuery('');
    // Do not steal focus from an input when its value changes the outline label.
    requestAnimationFrame(() => refs.current.get(selectedKey)?.scrollIntoView({ block: 'nearest' }));
  }, [selectedKey]);

  useEffect(() => {
    const count = selected?.childCount ?? 0;
    if (selectedKey && previousChildren.current.key === selectedKey && count > previousChildren.current.count) {
      setExpanded(old => ({ ...old, [selectedKey]: true }));
    }
    previousChildren.current = { key: selectedKey, count };
  }, [selectedKey, selected?.childCount]);

  const isOpen = (row: StructureRow) => query.trim() !== '' || (expanded[row.key] ?? row.depth < 2);
  function toggle(row: StructureRow) {
    const open = isOpen(row);
    setQuery('');
    setExpanded(old => ({ ...old, [row.key]: !open }));
    if (open && selected?.assetId === row.assetId && selected.path[row.depth] === row.nodeId) onSelect(row);
  }
  function focus(row?: StructureRow) { if (row) { setFocusedKey(row.key); refs.current.get(row.key)?.focus(); } }
  function keydown(event: KeyboardEvent, row: StructureRow, index: number) {
    if (!['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End', 'Enter', ' '].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'ArrowDown') focus(visible[index + 1]);
    if (event.key === 'ArrowUp') focus(visible[index - 1]);
    if (event.key === 'Home') focus(visible[0]);
    if (event.key === 'End') focus(visible.at(-1));
    if (event.key === 'ArrowRight' && row.childCount) { if (!isOpen(row)) toggle(row); else focus(visible[index + 1]); }
    if (event.key === 'ArrowLeft') { if (row.childCount && isOpen(row)) toggle(row); else focus(visible.find(item => item.key === row.parentKey)); }
    if (event.key === 'Enter' || event.key === ' ') onSelect(row);
  }
  return <section className="structure-panel" aria-label="구조 탐색">
    <div className="structure-heading"><h2>현재 구조</h2><span>{rows.length}</span><div className="structure-actions">
      <button className="icon-button" title="현재 항목 표시" aria-label="현재 항목 표시" disabled={!selected} onClick={() => {
        if (!selected) return;
        setQuery('');
        setExpanded(old => ({ ...old, ...Object.fromEntries(selected.path.map((_, index) => [structureKey(selected.assetId, selected.path.slice(0, index + 1)), true])) }));
        requestAnimationFrame(() => { focus(selected); refs.current.get(selected.key)?.scrollIntoView({ block: 'nearest' }); });
      }}><Crosshair size={16} /></button>
      <button className="icon-button" title="모두 접기" aria-label="모두 접기" disabled={!rows.length} onClick={() => {
        setQuery(''); setExpanded(Object.fromEntries(rows.map(row => [row.key, false])));
        const root = rows.find(row => row.assetId === selected?.assetId && row.depth === 0);
        if (root) onSelect(root);
      }}><ChevronsDownUp size={16} /></button>
    </div></div>
    <label className="structure-search"><Search size={15} /><input aria-label="구조 검색" placeholder="이름 또는 타입 검색" value={query} onChange={event => setQuery(event.target.value)} />
      {query && <button className="icon-button" title="검색 지우기" aria-label="검색 지우기" onClick={() => setQuery('')}><X size={14} /></button>}
    </label>
    <div className="structure-scroll"><div role="tree" aria-label="자산 구조" className="structure-tree">
      {visible.map((row, index) => <div key={row.key} role="treeitem" tabIndex={row.key === tabKey ? 0 : -1}
        aria-label={`${row.title} · ${row.typeLabel} · ${row.relation}`} aria-selected={row.key === selectedKey}
        aria-level={row.depth + 1} aria-posinset={row.position} aria-setsize={row.siblingCount}
        aria-expanded={row.childCount ? isOpen(row) : undefined}
        ref={element => { if (element) refs.current.set(row.key, element); else refs.current.delete(row.key); }}
        className={`tree-row ${row.key === selectedKey ? 'selected' : ''}`} style={{ '--tree-depth': Math.min(row.depth, 8) } as CSSProperties}
        onFocus={() => setFocusedKey(row.key)} onKeyDown={event => keydown(event, row, index)} onClick={() => onSelect(row)}>
        {row.childCount ? <button tabIndex={-1} className="tree-toggle" title={isOpen(row) ? '접기' : '펼치기'} aria-label={`${row.title} ${isOpen(row) ? '접기' : '펼치기'}`} onClick={event => { event.stopPropagation(); toggle(row); }}>{isOpen(row) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</button> : <span className="tree-toggle" />}
        {row.childCount ? <FolderTree className="tree-symbol" size={16} /> : <FileBox className="tree-symbol" size={16} />}
        <span className="tree-copy"><strong title={row.title}>{row.title}</strong><small title={`${row.typeLabel} · ${row.relation}`}>{row.typeLabel}{row.depth > 0 ? ` · ${row.relation}` : ''}</small></span>
        {row.childCount > 0 && <span className="tree-count">{row.childCount}</span>}
      </div>)}
    </div>{!visible.length && <p className="tree-empty">{query ? '검색 결과가 없습니다.' : '등록된 항목이 없습니다.'}</p>}</div>
  </section>;
}
