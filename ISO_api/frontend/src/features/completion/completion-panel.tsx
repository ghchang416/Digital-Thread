import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, CircleAlert, WandSparkles } from 'lucide-react';
import type { Catalog, Draft } from '../../shared/schema/types';
import { buildStructure } from '../../shared/draft/structure';
import { completeWorkplan } from '../../shared/api/client';
import { completionLabels, formatValue, groupIssues, workplanSteps } from './model';
import type { CompletionSettings } from './model';

const choices = [
  ['feedrate_reference', '이송 기준점', 'ToolReferencePoint', 'tcp'],
  ['pathmode', '경로 방식', 'PathmodeType', 'forward'],
  ['cutmode', '절삭 방향', 'CutmodeType', 'climb'],
  ['synchronize_spindle_with_feed', '주축·이송 동기화', '', 'false'],
  ['inhibit_feedrate_override', '이송 오버라이드 금지', '', 'false'],
  ['inhibit_spindle_override', '주축 오버라이드 금지', '', 'false'],
  ['coolant', '절삭유', '', 'false'],
  ['through_spindle_coolant', '주축 관통 절삭유', '', 'false'],
  ['chip_removal', '칩 제거', '', 'false'],
];
const numbers = [
  ['maximum_depth_of_cut', '최대 절삭 깊이'], ['overall_assembly_length', '공구 전체 길이'],
  ['effective_cutting_diameter', '유효 절삭 직경'], ['tool_functional_length', '공구 기능 길이'],
  ['chordal_tolerance', '현 공차'], ['scallop_height', '스캘럽 높이'],
  ['security_plane_z', '임시 안전 평면 Z'], ['feature_depth_z', '임시 깊이 평면 Z'],
];

export function CompletionPanel({ draft, catalog, workplanId, settings, onSettings, onApply, openIssue, hasRawErrors }: {
  draft: Draft; catalog: Catalog; workplanId: string; settings: CompletionSettings; hasRawErrors: boolean;
  onSettings: (settings: CompletionSettings) => void; onApply: (next: Draft, revision: number) => void;
  openIssue: (id: string, field: string | null) => void;
}) {
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const [busy, setBusy] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ count: number; skipped: number } | null>(null);
  const [filter, setFilter] = useState('all');
  const steps = workplanSteps(draft, workplanId);
  const rows = useMemo(() => buildStructure(draft, catalog, draft.assets), [draft, catalog]);
  const reachable = new Set(rows.filter(row => row.path.includes(workplanId) && row.path.some(id => steps.includes(id))).map(row => row.nodeId));
  const entries = (draft.completionEntries ?? []).filter(entry => reachable.has(entry.nodeId) && entry.fieldName in draft.nodes[entry.nodeId].fields);
  const filtered = entries.filter(entry => filter === 'all' || entry.kind === filter);
  const lookup = new Map(filtered.map(entry => [`${entry.nodeId}:${entry.fieldName}`, entry]));
  const groups = groupIssues(filtered.map(entry => ({ ...entry, itemId: null, code: entry.kind, message: entry.reason })), rows, draft);
  const numericInvalid = numbers.some(([name]) => {
    const value = settings.values[name]?.trim();
    return value && (!name.endsWith('_z') || settings.includePlaceholders) && (!Number.isFinite(Number(value)) || (!name.endsWith('_z') && Number(value) < 0));
  });
  const set = (name: string, value: string) => { setResult(null); onSettings({ ...settings, values: { ...settings.values, [name]: value } }); };
  async function apply() {
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); setError(''); setResult(null);
    try {
      const overrides: Record<string, string | number | boolean> = {};
      for (const [name, , enumType] of choices) if (settings.values[name]) overrides[name] = enumType ? settings.values[name] : settings.values[name] === 'true';
      for (const [name] of numbers) if (settings.values[name]?.trim() && (!name.endsWith('_z') || settings.includePlaceholders)) overrides[name] = Number(settings.values[name]);
      const response = await completeWorkplan(draft, workplanId, settings.includePlaceholders, overrides, abort.signal);
      if (abort.signal.aborted) return;
      onApply(response.draft, draft.revision);
      setResult({ count: response.addedCount, skipped: response.skipped.length });
    } catch (e) { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : '보완 요청 실패'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }
  return <section className="completion-panel">
    <div className="section-heading"><div><h2>누락값 보완</h2><span className="type-name">현재 워크플랜 · 밀링 워킹스텝 {steps.length}개 · 하위 워크플랜 제외</span></div></div>
    <p className="source-note">입력된 값은 유지됩니다. 자동 보완은 ISO 적합성이나 실제 가공 안전성을 보증하지 않습니다.</p>
    <fieldset disabled={busy} className="completion-settings">
      <details><summary>공통값 설정<span>빈 항목에만 적용</span></summary>
        <div className="completion-fields">{choices.map(([name, label, enumType, fallback]) => <label key={name}>{label}<small>{name}</small><select value={settings.values[name] ?? ''} onChange={e => set(name, e.target.value)}><option value="">기본값 · {fallback}</option>{(enumType ? catalog.enums[enumType] : ['true', 'false']).map(value => <option key={value} value={value}>{enumType ? value : value === 'true' ? '예 (true)' : '아니오 (false)'}</option>)}</select></label>)}</div>
        <p className="source-note">치수·공차는 CAM 및 프로젝트의 단위 기준으로 입력합니다. 평면 Z는 임시 객체 생성 시 적용되며 X/Y는 0으로 가정합니다.</p>
        <div className="completion-fields">{numbers.map(([name, label]) => <label key={name}>{label}<small>{name} · 실수</small><input inputMode="decimal" disabled={name.endsWith('_z') && !settings.includePlaceholders} value={settings.values[name] ?? ''} placeholder="미입력" onChange={e => set(name, e.target.value)} /></label>)}</div>
      </details>
      <label className="completion-check"><input type="checkbox" checked={settings.includePlaceholders} onChange={e => { onSettings({ ...settings, includePlaceholders: e.target.checked }); setAcknowledged(false); setResult(null); }} /><span>형상·좌표·치수 임시값 포함</span></label>
      {settings.includePlaceholders && <div className="completion-caution"><CircleAlert size={18} /><div><strong>작성용 임시 데이터</strong><p>누락된 피처·워크피스·평면과 0 치수·공차가 생성될 수 있습니다. 실제 가공에 사용하면 안 됩니다.</p><label className="completion-check"><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} /><span>임시값을 포함하며 별도 검토가 필요함을 확인했습니다.</span></label></div></div>}
    </fieldset>
    {numericInvalid && <p className="error-text" role="alert">공통 수치를 확인해 주세요. 치수·공차는 음수일 수 없습니다.</p>}
    {hasRawErrors && <p className="error-text">편집 중인 숫자 형식 오류를 먼저 수정해 주세요.</p>}
    <div className="completion-action"><button className="primary" disabled={busy || !steps.length || !!numericInvalid || hasRawErrors || (settings.includePlaceholders && !acknowledged)} onClick={apply}><WandSparkles size={16} />{busy ? '보완 중' : '누락값 일괄 보완'}</button><span className="type-name">가공 타입·자산 참조·NC T 번호는 자동 생성하지 않습니다.</span></div>
    {error && <p className="error-text" role="alert">{error}</p>}
    {result && <p role="status">{result.count}개 항목 보완 · 다른 워킹스텝과 공유된 객체 {result.skipped}개 제외. XML 검토에서 남은 필수 항목을 확인해 주세요.</p>}
    {result && draft.toolLinks?.some(link => link.workplanNodeId === workplanId) && <p className="source-note">공구 값이 보완되면 기존 13399 공구 자산과 달라질 수 있습니다. NC·공구 연결의 재확인 상태를 확인해 주세요.</p>}
    <div className="completion-history"><div className="section-heading"><h3>보완 이력 <span className="type-name">{entries.length}개</span></h3><select aria-label="보완 이력 필터" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">전체</option>{Object.entries(completionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      {!groups.length && <p className="muted">표시할 보완 이력이 없습니다.</p>}
      {groups.map(group => <details className="completion-group" key={group.key}><summary>{group.title}<span>{group.issues.length}개</span></summary>{group.issues.map(issue => {
        const entry = lookup.get(`${issue.nodeId}:${issue.fieldName}`)!;
        const current = draft.nodes[entry.nodeId].fields[entry.fieldName];
        const changed = JSON.stringify(current) !== JSON.stringify(entry.value);
        return <button className="completion-entry" key={`${entry.nodeId}:${entry.fieldName}`} onClick={() => openIssue(entry.nodeId, entry.fieldName)} title={entry.reason}><span><small>{issue.context}</small><strong>{entry.fieldName}</strong><span className={`completion-badge ${entry.kind}`}>{completionLabels[entry.kind]}{changed ? ' · 보완 후 변경됨' : ''}</span></span><span className="completion-value">{formatValue(current, draft)}{changed && <small>최초: {formatValue(entry.value, draft)}</small>}</span><ArrowRight size={16} /></button>;
      })}</details>)}
    </div>
  </section>;
}
