import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, CircleCheck, CircleAlert, Download, FileCode2, Layers, Plus, Settings2, Trash2, Box, RefreshCw, PanelLeft, Upload, Pencil, Files, Wrench, Link2 } from 'lucide-react';
import { fetchCatalog, reviewAsset } from './shared/api/client';
import { applyCommand, nodeTitle } from './shared/draft/model';
import type { Command } from './shared/draft/model';
import type { AssetDraft, Catalog, Draft } from './shared/schema/types';
import { activeRawErrors, currentReview } from './shared/draft/review-state';
import type { ReviewSnapshot } from './shared/draft/review-state';
import { NodeEditor } from './shared/schema/node-editor';
import { buildStructure, resolveSelection } from './shared/draft/structure';
import type { StructureRow } from './shared/draft/structure';
import { StructureTree } from './shared/ui/structure-tree';
import type { RecoveryRecord, WorkspaceData } from './shared/draft/workspace';
import { readRecovery, useRecovery } from './shared/draft/recovery';
import { CamImportEditor } from './features/cam/cam-import';
import { emptyCamSession } from './features/cam/types';
import { applyCamImport } from './features/cam/import';
import { FileManager } from './features/files/file-manager';
import { NcEditor } from './features/files/nc-editor';
import { addFileAsset, bindFile, emptyNcSession, ncSignature } from './features/files/model';
import { ResetDialog } from './shared/ui/reset-dialog';
import { FilePlus2 } from 'lucide-react';
import { CompletionPanel } from './features/completion/completion-panel';
import { emptySettings } from './features/completion/model';
import { GroupedIssues } from './shared/ui/grouped-issues';
import { ExportPanel } from './features/export/export-panel';
import { OperatorPanel } from './features/operator/operator-panel';
import { operatorLabels } from './features/operator/labels';
import { isRef } from './shared/schema/types';
import { SettingsPanel } from './features/operator/settings';
import { addWorkplan, createAsset, newWorkspace, readPreferences } from './features/operator/model';
import { assetReferenceUsers } from './shared/draft/references';
import { ManualToolPanel } from './features/manual/tool-panel';
import { ManualStepPanel } from './features/manual/step-panel';
import type { ManualResult } from './shared/api/client';

const sections = [
  { role: 'project', name: '프로젝트', icon: Layers, type: 'DtProject' },
  { role: 'machine', name: '머신 툴', icon: Settings2, type: 'DtMachineTool' },
  { role: 'material', name: '마테리얼', icon: Box, type: 'DtMaterial' },
  { role: 'file', name: '파일', icon: Files, type: 'DtFile' },
  { role: 'tool', name: '공구 · 13399', icon: Wrench, type: 'DtCuttingTool13399' },
] as const;

function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Workspace({ catalog, initial, sequence, restored, onReset }: { catalog: Catalog; initial: WorkspaceData; sequence: number; restored: boolean; onReset: (record: RecoveryRecord) => void }) {
  const [data, setData] = useState(initial);
  const latestData = useRef(data); latestData.current = data;
  const { draft, role, assetId, path, extraFields, rawInputs } = data;
  const recovery = useRecovery(data, sequence);
  const screen = data.screen ?? 'detail';
  const setScreen = (screen: WorkspaceData['screen']) => setData(old => ({ ...old, screen }));
  const [recoveryNotice, setRecoveryNotice] = useState(restored);
  const [camView, setCamView] = useState(false);
  const [ncView, setNcView] = useState(false);
  const [completionView, setCompletionView] = useState(false);
  const [manualView, setManualView] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const setDraft = (value: Draft | ((old: Draft) => Draft)) => setData(old => ({ ...old, draft: typeof value === 'function' ? value(old.draft) : value }));
  const setRole = (value: AssetDraft['role']) => { setManualView(false); setCamView(false); setNcView(false); setCompletionView(false); setData(old => ({ ...old, role: value })); };
  const setAssetId = (value: string) => setData(old => ({ ...old, assetId: value }));
  const setPath = (value: string[]) => { setManualView(false); setCamView(false); setNcView(false); setCompletionView(false); setData(old => ({ ...old, path: value })); };
  const setExtraFields = (update: (old: Record<string, string[]>) => Record<string, string[]>) => setData(old => ({ ...old, extraFields: update(old.extraFields) }));
  const setRawInputs = (update: (old: Record<string, string>) => Record<string, string>) => setData(old => ({ ...old, rawInputs: update(old.rawInputs) }));
  const [structureOpen, setStructureOpen] = useState(false);
  const [preview, setPreview] = useState<ReviewSnapshot | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const assets = draft.assets.filter(a => a.role === role);
  const rows = useMemo(() => buildStructure(draft, catalog, draft.assets.filter(a => a.role === role)), [draft, catalog, role]);
  const reviewRows = useMemo(() => buildStructure(draft, catalog, draft.assets), [draft, catalog]);
  const selected = resolveSelection(rows, assetId, path);
  const asset = assets.find(a => a.assetNodeId === selected?.assetId);
  const root = asset ? draft.nodes[asset.assetNodeId] : undefined;
  const validPath = selected?.path ?? [];
  const nodeId = selected?.nodeId;
  const selectedSection = sections.find(s => s.role === role)!;
  const currentPreview = currentReview(draft, asset?.assetNodeId, rawInputs, preview);
  const rawErrors = activeRawErrors(draft, rawInputs);
  const workplanId = [...validPath].reverse().find(id => draft.nodes[id]?.typeId === 'Workplan');
  const camSession = workplanId ? data.camSessions[workplanId] ?? emptyCamSession() : undefined;
  const ncSession = workplanId ? data.ncSessions?.[workplanId] ?? emptyNcSession() : undefined;
  const machineRef = asset && draft.nodes[asset.elementNodeId]?.fields.machine_tool;
  const toolUsages = (draft.toolLinks ?? []).filter(link => link.assetNodeId === asset?.assetNodeId);
  const camOrigins = data.camImports.flatMap(entry => entry.candidates.flatMap(candidate => candidate.origins)).filter(origin => origin.nodeId === nodeId);
  const camSource = data.camImports.find(entry => entry.candidates.some(candidate => candidate.rootNodeId === nodeId));
  const dispatch = (command: Command) => {
    if (command.kind === 'delete-asset' && assetReferenceUsers(draft, command.assetNodeId).length) { setError('다른 객체에서 참조 중인 자산입니다. 참조를 먼저 해제해 주세요.'); return; }
    if (command.kind === 'delete-asset' && draft.manualToolLinks?.some(link => link.assetNodeId === command.assetNodeId && draft.nodes[link.stepNodeId])) { setError('워킹스텝에서 사용하는 공구입니다. 직접 작성 화면에서 참조를 해제해 주세요.'); return; }
    if (command.kind === 'delete-asset' && draft.toolLinks?.some(link => link.assetNodeId === command.assetNodeId && link.stepNodeIds.some(id => draft.nodes[id]))) { setError('워킹스텝에서 사용하는 공구는 삭제할 수 없습니다.'); return; }
    setDraft(current => applyCommand(current, command)); setError('');
  };
  const setRaw = (key: string, value?: string) => setRawInputs(old => { const next = { ...old }; if (value === undefined) delete next[key]; else next[key] = value; return next; });
  function selectRow(row: StructureRow) {
    setAssetId(row.assetId); setPath(row.path); if (screen === 'export' || screen === 'settings') setScreen('detail'); setStructureOpen(false);
    if (window.matchMedia('(max-width: 760px)').matches) requestAnimationFrame(() => document.getElementById('structure-trigger')?.focus());
  }
  function navigate(id: string) {
    const row = rows.find(item => item.assetId === asset?.assetNodeId && item.nodeId === id);
    if (row) selectRow(row);
  }
  function openAsset(id: string) {
    const target = draft.assets.find(item => item.assetNodeId === id);
    if (target) { setRole(target.role); setAssetId(id); setPath([target.elementNodeId]); }
  }
  function openIssue(target: string, field: string | null) {
    setScreen('detail');
    const row = reviewRows.find(item => item.nodeId === target);
    const rootAsset = draft.assets.find(item => item.assetNodeId === target);
    const targetAsset = row && draft.assets.find(item => item.assetNodeId === row.assetId);
    if (row && targetAsset) { setRole(targetAsset.role); selectRow(row); }
    else if (rootAsset) openAsset(rootAsset.assetNodeId);
    else navigate(target);
    requestAnimationFrame(() => {
      if (rootAsset) {
        const details = document.getElementById('asset-details') as HTMLDetailsElement | null;
        if (details) { details.open = true; details.scrollIntoView({ block: 'center' }); }
      } else document.getElementById(`row-${target}-${field}`)?.scrollIntoView({ block: 'center' });
    });
  }
  function applyPrepared(result: ManualResult, expectedRevision: number) {
    const current = latestData.current;
    if (current.draft.draftId !== result.draft.draftId || current.draft.revision !== expectedRevision || activeRawErrors(current.draft, current.rawInputs).length) throw new Error('처리 중 입력이 변경되었습니다. 다시 적용해 주세요.');
    setDraft(result.draft); setPreview(null);
    if (result.assetNodeId) { setAssetId(result.assetNodeId); setPath([]); }
  }
  function openWorkflow(id: string, tab: 'cam' | 'completion' | 'nc' | 'detail' | 'manual') {
    const row = reviewRows.find(item => item.nodeId === id);
    if (!row) return;
    setRole('project'); selectRow(row); setScreen('detail');
    setCamView(tab === 'cam'); setCompletionView(tab === 'completion'); setNcView(tab === 'nc');
    setManualView(tab === 'manual');
  }
  return <div className="app-shell">
    <header className="app-header"><button id="structure-trigger" className="icon-button structure-trigger" title="구조 탐색" aria-label="구조 탐색" aria-expanded={structureOpen} aria-controls="structure-sidebar" onClick={() => setStructureOpen(!structureOpen)}><PanelLeft size={20} /></button><div className="brand-mark"><Layers size={23} /><div><strong>DT 프로젝트 생성기</strong><small>ISO 14649 · v31</small></div></div><span className={`status ${recovery.error ? 'error-text' : ''}`} aria-live="polite">{recovery.error ? <CircleAlert size={15} /> : <CircleCheck size={15} />}{recovery.error ? '로컬 저장 실패' : recovery.pending ? '로컬 저장 중' : '로컬 저장됨'}</span><button className="secondary" title="객체 데이터만 내보내기 · CAM 원본 제외" disabled={rawErrors.length > 0} onClick={() => download('project-draft.json', JSON.stringify(draft, null, 2), 'application/json')}><Download size={16} />초안 JSON</button></header>
    {resetOpen && <ResetDialog assetCount={draft.assets.length} fileCount={Object.keys(data.files).length} onClose={() => setResetOpen(false)} onConfirm={async () => { const record = await recovery.reset(newWorkspace(catalog, readPreferences())); onReset(record); }} />}
    <aside id="structure-sidebar" className={`sidebar ${structureOpen ? 'structure-open' : ''}`}><span className="nav-caption">프로젝트 구성</span><div className="editor-tabs"><button aria-pressed={screen === 'operator'} onClick={() => setScreen('operator')}>작업자</button><button aria-pressed={screen === 'detail'} onClick={() => setScreen('detail')}>상세 편집</button></div><button className="secondary new-project" title="작성 중인 내용을 초기화하고 새 프로젝트 시작" onClick={() => setResetOpen(true)}><FilePlus2 size={16} />새 프로젝트</button><nav aria-label="자산 종류">{sections.map(section => <button key={section.role} className={role === section.role ? 'active' : ''} aria-current={role === section.role ? 'page' : undefined} onClick={() => { setRole(section.role); setPath([]); if (screen === 'export' || screen === 'settings') setScreen('operator'); }}><section.icon size={18} /><span>{section.name}</span><span className="count">{draft.assets.filter(a => a.role === section.role).length}</span></button>)}</nav><StructureTree rows={rows} selectedKey={selected?.key} onSelect={selectRow} /><div className="sidebar-bottom"><button className="secondary" onClick={() => setScreen('export')}><FileCode2 size={16} />전체 XML 검토</button><button className="text-button" onClick={() => setScreen('settings')}><Settings2 size={16} />설정</button><span className="type-name">검토용 XML · 서버 저장 없음</span></div></aside>
    <main>
      {recovery.error && <div className="recovery-notice error-text" role="alert"><span>{recovery.error}</span><button className="secondary" onClick={recovery.retry}><RefreshCw size={15} />다시 저장</button></div>}
      {recoveryNotice && <div className="recovery-notice" role="status"><span>이 브라우저에 저장된 입력 내용과 CAM 원본을 복구했습니다.</span><button className="text-button" onClick={() => setRecoveryNotice(false)}>확인</button></div>}
      {screen === 'export' ? <ExportPanel data={data} openIssue={openIssue} /> : screen === 'settings' ? <SettingsPanel /> : screen === 'operator' && role === 'project' ? <OperatorPanel draft={draft} catalog={catalog} workplanId={workplanId} dispatch={dispatch} select={id => { const row = reviewRows.find(r => r.nodeId === id); if (row) selectRow(row); }} workflow={openWorkflow} addWorkplan={id => setDraft(current => addWorkplan(current, id))} openAsset={openAsset} review={() => setScreen('export')} applyMaterial={(ids, policyId, targetAssetNodeId) => setDraft(current => ids.reduce((next, nodeId) => applyCommand(next, { kind: 'reference', nodeId, policyId, targetAssetNodeId, policyHash: catalog.referencePolicyHash! }), current))} /> : <>
      {screen === 'detail' && <button className="text-button" onClick={() => setScreen('operator')}>작업자 화면으로 돌아가기</button>}
      <div className="page-heading"><div><h1>{selectedSection.name}</h1>{asset && <span className="type-name">{nodeTitle(draft.nodes[asset.elementNodeId], catalog)}</span>}</div>{(role === 'machine' || role === 'material') && <button className="primary" onClick={() => { const next = createAsset(draft, role); setDraft(next); setAssetId(next.assets.at(-1)!.assetNodeId); setPath([]); }}><Plus size={17} />{selectedSection.name} 추가</button>}</div>
      {role === 'tool' && <ManualToolPanel key={asset?.assetNodeId ?? 'new-tool'} draft={draft} catalog={catalog} assetId={asset?.assetNodeId} disabled={rawErrors.length > 0} onApply={applyPrepared} onDetail={() => { setScreen('detail'); if (asset) setPath([asset.elementNodeId]); }} />}
      {role === 'file' && <FileManager draft={draft} files={data.files} selectedAssetId={asset?.assetNodeId} onAdd={(files, purpose) => setData(old => {
        const next = files.reduce((current, file) => addFileAsset(current, file, purpose), old.draft);
        return { ...old, draft: next, assetId: next.assets.at(-1)!.assetNodeId, path: [], files: { ...old.files, ...Object.fromEntries(files.map(file => [file.fileId, file])) } };
      })} onBind={(id, wp) => setDraft(bindFile(draft, id, wp))} onSelect={id => { setAssetId(id); setPath([]); }} />}
      {assets.length > 0 ? <>
        {root && <details id="asset-details" className="asset-details" key={root.nodeId} open={validPath.length === 1}><summary>자산 정보<span>{String(root.fields.id ?? 'ID 미입력')}</span></summary><section className="asset-meta"><label>글로벌 자산 ID<input value={String(root.fields.asset_global_id ?? '')} onChange={e => dispatch({ kind: 'set', nodeId: root.nodeId, field: 'asset_global_id', value: e.target.value })} /></label><label>자산 ID<input value={String(root.fields.id ?? '')} onChange={e => dispatch({ kind: 'set', nodeId: root.nodeId, field: 'id', value: e.target.value })} /></label>{role !== 'project' && <button className="icon-button" title="자산 삭제" aria-label="자산 삭제" onClick={() => { if (confirm('이 자산의 입력 내용을 삭제할까요?')) { dispatch({ kind: 'delete-asset', assetNodeId: root.nodeId }); setPath([]); } }}><Trash2 size={17} /></button>}</section></details>}
        <nav className="breadcrumbs" aria-label="객체 경로">{validPath.map((id, index) => <span key={`${id}-${index}`}>{index > 0 && <ChevronRight size={14} />}<button aria-current={index === validPath.length - 1 ? 'location' : undefined} onClick={() => setPath(validPath.slice(0, index + 1))}>{nodeTitle(draft.nodes[id], catalog)}</button></span>)}</nav>
        {screen === 'operator' && (role === 'machine' || role === 'material') && <div className="asset-tabs">{rows.filter(row => row.assetId === asset?.assetNodeId).map(row => <button key={row.key} className={row.nodeId === nodeId ? 'selected' : ''} onClick={() => selectRow(row)}>{row.title}</button>)}<button className="text-button" onClick={() => setScreen('detail')}><Pencil size={15} />상세 편집</button></div>}
        {screen === 'operator' && role === 'machine' && asset && !isRef(machineRef) && <button className="secondary" onClick={() => dispatch({ kind: 'attach', nodeId: asset.elementNodeId, field: 'machine_tool', typeId: 'MachineToolRequirements', repeated: false })}><Plus size={16} />설비 사양 입력</button>}
        {toolUsages.map(link => <div className="tool-usage" key={`${link.workplanNodeId}:${link.toolTag}`}><strong>{link.toolTag}</strong><span>{String(draft.nodes[link.workplanNodeId]?.fields.its_id || '워크플랜')} · 워킹스텝 {link.stepNodeIds.length}개</span><button className="text-button" onClick={() => {
          const row = buildStructure(draft, catalog, draft.assets.filter(a => a.role === 'project')).find(row => row.nodeId === link.workplanNodeId);
          if (row) { setRole('project'); selectRow(row); setNcView(true); }
        }}><Link2 size={15} />연결 확인</button></div>)}
        {role === 'file' && <p className="source-note">로컬 파일 자산 · 파일 저장 ID 미발급</p>}
        {workplanId && <div className="editor-tabs" role="group" aria-label="워크플랜 편집 모드"><button aria-pressed={!camView && !ncView && !completionView && !manualView} onClick={() => openWorkflow(workplanId, 'detail')}><Pencil size={15} />항목 편집</button><button aria-pressed={camView} onClick={() => openWorkflow(workplanId, 'cam')}><Upload size={15} />CAM 가져오기</button><button aria-pressed={manualView} onClick={() => openWorkflow(workplanId, 'manual')}><Plus size={15} />직접 작성</button><button aria-pressed={completionView} onClick={() => openWorkflow(workplanId, 'completion')}><Settings2 size={15} />누락값 보완</button><button aria-pressed={ncView} onClick={() => openWorkflow(workplanId, 'nc')}><Link2 size={15} />NC·공구 연결</button><span className="type-name">{nodeTitle(draft.nodes[workplanId], catalog)}</span></div>}
        {manualView && workplanId ? <ManualStepPanel key={workplanId} draft={draft} catalog={catalog} workplanId={workplanId} disabled={rawErrors.length > 0} onApply={applyPrepared} dispatch={dispatch} onDetail={id => openWorkflow(id, 'detail')} openTools={() => { setRole('tool'); setScreen('operator'); setPath([]); }} openNc={() => openWorkflow(workplanId, 'nc')} openCompletion={() => openWorkflow(workplanId, 'completion')} /> : completionView && workplanId ? <CompletionPanel key={workplanId} draft={draft} catalog={catalog} workplanId={workplanId} hasRawErrors={rawErrors.length > 0} settings={data.completionSettings?.[workplanId] ?? emptySettings()} onSettings={settings => setData(old => ({ ...old, completionSettings: { ...old.completionSettings, [workplanId]: settings } }))} openIssue={openIssue} onApply={(next, expectedRevision) => {
          if (latestData.current.draft.revision !== expectedRevision || activeRawErrors(latestData.current.draft, latestData.current.rawInputs).length) throw new Error('처리 중 입력이 변경되었습니다. 다시 보완해 주세요.');
          setDraft(next); setPreview(null);
        }} /> : ncView && workplanId && ncSession ? <NcEditor key={workplanId} draft={draft} workplanId={workplanId} files={data.files} session={ncSession} hasRawErrors={rawErrors.length > 0} openFiles={() => { setRole('file'); setPath([]); }} onChange={session => setData(old => ({ ...old, ncSessions: { ...old.ncSessions, [workplanId]: session } }))} onApply={(next, expectedRevision, session) => {
          if (latestData.current.draft.revision !== expectedRevision) throw new Error('처리 중 입력이 변경되었습니다. 다시 연결해 주세요.');
          setData(old => ({ ...old, draft: next, ncSessions: { ...old.ncSessions, [workplanId]: { ...session, appliedSignature: ncSignature(next, workplanId, session) } } }));
          setPreview(null);
        }} /> : camView && workplanId && camSession ? <CamImportEditor key={workplanId} catalog={catalog} workplanId={workplanId} title={nodeTitle(draft.nodes[workplanId], catalog)} session={camSession} files={data.files} appliedIds={new Set(Object.keys(draft.nodes))} onChange={(session, files = []) => setData(old => ({ ...old, camSessions: { ...old.camSessions, [workplanId]: session }, files: { ...old.files, ...Object.fromEntries(files.map(file => [file.fileId, file])) } }))} onApply={() => {
          const applied = applyCamImport(draft, workplanId, camSession, data.camImports);
          setData(old => ({ ...old, draft: applied.draft, camImports: [...old.camImports, applied.entry], camSessions: { ...old.camSessions, [workplanId]: { ...camSession, selectedIds: [], acknowledged: false } }, path: [...validPath.slice(0, validPath.indexOf(workplanId) + 1), applied.entry.candidates[0].rootNodeId] }));
          setCamView(false);
        }} /> : <>{camSource && <p className="source-note">CAM 원본 · {camSource.fileResults.find(file => camSource.candidates.some(candidate => candidate.rootNodeId === nodeId && candidate.fileId === file.fileId))?.name} · {camSource.camType === 'nx' ? 'NX' : 'PowerMill'}</p>}{nodeId && <NodeEditor key={nodeId} draft={draft} catalog={catalog} nodeId={nodeId} labels={screen === 'operator' ? operatorLabels : undefined} dispatch={dispatch} navigate={navigate} openAsset={openAsset} rawInputs={rawInputs} setRaw={setRaw} extras={extraFields[nodeId] ?? []} setExtras={values => setExtraFields(old => ({ ...old, [nodeId]: values }))} origins={camOrigins} hiddenFields={screen === 'operator' && (role === 'machine' || role === 'material') ? ['element_id', 'category'] : role === 'file' ? ['value', 'reference', 'category', 'path', 'content_type'] : role === 'tool' && toolUsages.length ? ['element_id'] : []} />}</>}
        <section className="preview-section" hidden={(camView || ncView) && !!workplanId}><div className="section-heading"><div><h2>XML 구조 검토</h2><span className="type-name">모델 메타데이터 검사 · 최종 검증 전</span></div><button className="secondary" disabled={checking || rawErrors.length > 0} onClick={async () => { if (!asset) return; const revision = draft.revision; const currentAsset = asset.assetNodeId; setChecking(true); setError(''); try { setPreview({ revision, assetId: currentAsset, result: await reviewAsset(draft, currentAsset) }); } catch (e) { setError(e instanceof Error ? e.message : '검토 요청 실패'); } finally { setChecking(false); } }}><FileCode2 size={16} />{checking ? '검토 중' : 'XML 미리보기'}</button></div>
          {rawErrors.length > 0 && <p role="alert" className="error-text">숫자 형식이 올바르지 않은 입력 {rawErrors.length}개가 있습니다.</p>}
          {error && <p className="error-text" role="alert">{error}</p>}
          {preview && !currentPreview && <p className="muted">입력이 변경되었습니다. 다시 검토해 주세요.</p>}
          {currentPreview && <><div className={`review-status ${currentPreview.valid ? '' : 'error-text'}`}>{currentPreview.valid ? currentPreview.pendingStorage?.length ? '입력 메타데이터 검사 통과 · 파일 저장 대기 · 검토용 XML' : '구조 검사 통과 · 최종 저장 불가' : `${currentPreview.issues.length}개 항목 확인 필요`}</div>
            <GroupedIssues issues={currentPreview.issues} rows={reviewRows} draft={draft} openIssue={openIssue} />
            {currentPreview.pendingStorage?.map(item => <div className="source-note" role="status" key={`${item.nodeId}:${item.fieldName}`}><p className="completion-review-note"><CircleAlert size={17} />파일 저장 대기 · {item.nodeId ? String(draft.nodes[item.nodeId]?.fields.path || draft.nodes[item.nodeId]?.fields.element_id || '파일') : '파일'}</p><p>{item.message} 완성본이 아니므로 최종 저장·플랫폼 등록에는 사용할 수 없습니다.</p></div>)}
            {!!currentPreview.warnings?.length && <><p className="completion-review-note"><CircleAlert size={17} />보완 이력 {currentPreview.warnings.length}개 · 실제 가공 적합성 미검증</p><GroupedIssues issues={currentPreview.warnings} rows={reviewRows} draft={draft} openIssue={openIssue} warning /></>}
            {currentPreview.artifacts.map(artifact => <details key={artifact.assetNodeId} open><summary>{artifact.omittedFields?.length ? '검토용 XML · 저장 ID 생략' : '생성 XML · 검토용'}</summary><pre>{artifact.xml}</pre><button className="secondary" onClick={() => download('asset-preview.xml', artifact.xml, 'application/xml')}><Download size={15} />검토 XML 다운로드</button></details>)}
          </>}
        </section>
      </> : role === 'file' ? null : <section className="empty-state"><selectedSection.icon size={35} /><h2>등록된 {selectedSection.name}이 없습니다.</h2>{role === 'tool' ? <button className="secondary" onClick={() => { setRole('project'); setPath([]); }}>프로젝트로 이동</button> : <button className="primary" onClick={() => { if (role === 'machine' || role === 'material') { const next = createAsset(draft, role); setDraft(next); setAssetId(next.assets.at(-1)!.assetNodeId); } setPath([]); }}><Plus size={17} />{selectedSection.name} 추가</button>}</section>}
      </>}
    </main>
  </div>;
}

export default function App() {
  const query = useQuery({ queryKey: ['creator-schema'], queryFn: fetchCatalog, staleTime: Infinity, retry: 1 });
  if (query.isPending) return <main className="connection"><Layers size={28} /><h1>프로젝트 생성기</h1><p>스키마 불러오는 중...</p></main>;
  if (query.isError) return <main className="connection"><CircleAlert size={28} /><h1>API 연결 실패</h1><p>{query.error.message}</p><button className="primary" onClick={() => query.refetch()}><RefreshCw size={16} />다시 연결</button></main>;
  return <RecoveryGate catalog={query.data} />;
}

function RecoveryGate({ catalog }: { catalog: Catalog }) {
  const [state, setState] = useState<{ record: RecoveryRecord | null; fresh?: boolean; initial?: WorkspaceData } | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    readRecovery(catalog).then(record => { if (active) setState({ record, initial: record ? undefined : newWorkspace(catalog, readPreferences()) }); }).catch(e => { if (active) setError(e instanceof Error ? e.message : '로컬 복구에 실패했습니다.'); });
    return () => { active = false; };
  }, [catalog, attempt]);
  if (!state) return <main className="connection"><Layers size={28} /><h1>프로젝트 생성기</h1>{error ? <><p className="error-text" role="alert">{error}</p><button className="secondary" onClick={() => { setError(''); setAttempt(value => value + 1); }}><RefreshCw size={16} />복구 다시 시도</button></> : <p>로컬 초안 확인 중…</p>}</main>;
  return <Workspace key={state.record?.data.draft.draftId ?? 'initial'} catalog={catalog} initial={state.record?.data ?? state.initial!} sequence={state.record?.sequence ?? 0} restored={!!state.record && !state.fresh} onReset={record => setState({ record, fresh: true })} />;
}
