import type { Catalog, Draft, FieldValue } from '../../shared/schema/types';
import { isRef } from '../../shared/schema/types';
import type { RecoveryRecord, WorkspaceData } from '../../shared/draft/workspace';
import { validateRecovery } from '../../shared/draft/workspace';
import type { ElsCandidate, ElsMetadata } from './contracts';
import { ELS_FIELDS, hasUnintegratedElsData } from './contracts';

export interface ElsWorkspaceData extends WorkspaceData { elsMetadata: ElsMetadata }
export interface ElsRecoveryRecord {
  formatVersion: 2; requiredCapabilities: ['els-import-v1'];
  sequence: number; savedAt: string; data: ElsWorkspaceData;
}
export type WorkspaceSnapshot = RecoveryRecord | ElsRecoveryRecord;
export type RecoverableWorkspace = WorkspaceData | ElsWorkspaceData;

export const jsonEqual = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => jsonEqual(v, b[i]));
  const left = a as Record<string, unknown>, right = b as Record<string, unknown>;
  return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every(key => Object.hasOwn(right, key) && jsonEqual(left[key], right[key]));
};
const requireValue = (ok: unknown, code: string): void => { if (!ok) throw new Error(`ELS_${code}: 기존 데이터는 보존했습니다.`); };
const text = (v: unknown, max = 255): v is string => typeof v === 'string' && v.trim().length > 0 && v.length <= max;
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const unique = (values: string[]) => values.length === new Set(values).size;
const keys = (value: object, allowed: string[]) => requireValue(value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).every(k => allowed.includes(k)), 'UNKNOWN_FIELD');
const scalar = (v: unknown) => typeof v === 'string' || typeof v === 'boolean' || (typeof v === 'number' && Number.isFinite(v));
const fieldValue = (v: FieldValue): boolean => scalar(v) || (isRef(v) && text(v.$node)) || (Array.isArray(v) && v.every(item => isRef(item) ? text(item.$node) : !!item && text(item.itemId) && scalar(item.value)));

export function snapshotOf(data: RecoverableWorkspace, sequence: number): WorkspaceSnapshot {
  const common = { sequence, savedAt: new Date().toISOString() };
  return 'elsMetadata' in data
    ? { ...common, formatVersion: 2, requiredCapabilities: ['els-import-v1'], data }
    : { ...common, formatVersion: 1, data };
}

function reachableNodes(draft: Draft, root: string): Set<string> {
  const seen = new Set<string>();
  let visits = 0;
  const visit = (id: string, ancestors: Set<string>) => {
    requireValue(++visits <= 10000 && ancestors.size < 64 && !ancestors.has(id) && draft.nodes[id], 'GRAPH_BUDGET');
    seen.add(id);
    const next = new Set(ancestors).add(id);
    for (const value of Object.values(draft.nodes[id].fields)) for (const item of Array.isArray(value) ? value : [value]) if (isRef(item)) visit(item.$node, next);
  };
  visit(root, new Set());
  return seen;
}

// Local corruption/ownership checks only. Server review still validates profile semantics,
// tool synchronization, scoped confirmation hashes and XML before any download.
export function validateElsMetadata(draft: Draft, metadata: ElsMetadata, catalog: Catalog, profileHash: string): void {
  requireValue(hash(profileHash) && metadata && typeof metadata === 'object', 'PROFILE_REQUIRED');
  requireValue(Object.keys(metadata).length === ELS_FIELDS.length && Object.keys(metadata).every(k => (ELS_FIELDS as readonly string[]).includes(k)), 'METADATA_FIELDS');
  for (const name of ELS_FIELDS) requireValue(Array.isArray(metadata[name]) && metadata[name].length <= (name === 'elsOrigins' ? 20000 : 1000), 'METADATA_LIMIT');
  requireValue(new TextEncoder().encode(JSON.stringify({ ...draft, ...metadata })).length <= 1835008, 'DRAFT_BUDGET');
  requireValue(metadata.elsImports.length > 0 && unique(metadata.elsImports.map(i => i.importEntryId)), 'IMPORT_IDENTITY');
  const imports = new Map(metadata.elsImports.map(i => [i.importEntryId, i]));
  const rows = new Map(metadata.elsImports.map(i => [i.importEntryId, new Map(i.sourceRows.map(r => [r.rowId, r]))]));
  for (const item of metadata.elsImports) {
    keys(item, ['importEntryId', 'sourceSha256', 'sourceSchemaHash', 'profileHash', 'sourceName', 'readerVersion', 'selection', 'sourceRows', 'decisions']);
    requireValue(text(item.importEntryId) && hash(item.sourceSha256) && hash(item.sourceSchemaHash) && item.profileHash === profileHash && text(item.sourceName) && text(item.readerVersion), 'IMPORT_HEADER');
    requireValue(item.sourceRows.length > 0 && item.sourceRows.length <= 1000 && unique(item.sourceRows.map(r => r.rowId)), 'SOURCE_ROWS');
    for (const row of item.sourceRows) {
      keys(row, ['rowId', 'table', 'values']);
      requireValue(text(row.rowId) && ['Part_Info', 'Operation_Info', 'Operation_Machining', 'Machine_Milling', 'Tool_Milling', 'Part_File', 'Machine_File', 'Tool_File'].includes(row.table), 'SOURCE_ROW');
      const cells = Object.entries(row.values);
      requireValue(cells.length > 0 && cells.length <= 64 && cells.every(([key, value]) => text(key) && !['__proto__', 'constructor', 'prototype'].includes(key) && (value === null || (scalar(value) && (typeof value !== 'string' || value.length <= 4096) && (typeof value !== 'number' || !Number.isInteger(value) || Number.isSafeInteger(value))))), 'SOURCE_CELLS');
    }
    const s = item.selection;
    keys(s, ['partNo', 'partRevision', 'opNo', 'programNo', 'programRevision', 'orderedRowIds', 'excludedRows', 'orderReason']);
    for (const row of s.excludedRows) keys(row, ['rowId', 'reason']);
    requireValue([s.partNo, s.partRevision, s.opNo, s.programNo, s.programRevision].every(v => text(v)) && s.orderedRowIds.length > 0 && s.orderedRowIds.length <= 300 && s.excludedRows.length <= 1000, 'SELECTION');
    const selected = [...s.orderedRowIds, ...s.excludedRows.map(r => r.rowId)];
    requireValue(unique(selected) && s.excludedRows.every(r => text(r.reason, 1000)) && (s.orderReason == null || text(s.orderReason, 1000)), 'SELECTION_ROWS');
    for (const id of selected) {
      const row = rows.get(item.importEntryId)?.get(id);
      requireValue(row?.table === 'Operation_Machining', 'SELECTION_SOURCE');
      const cells = Object.fromEntries(Object.entries(row!.values).map(([k, v]) => [k.normalize('NFC').toLowerCase(), v]));
      requireValue(['part_no', 'part_rev', 'op_no', 'pgmno', 'revno'].every((key, index) => cells[key] === [s.partNo, s.partRevision, s.opNo, s.programNo, s.programRevision][index]), 'SOURCE_SCOPE');
    }
    if (item.decisions) {
      const d = item.decisions;
      keys(d, ['templateId', 'templateReason', 'millingConfirmed', 'valueChoices', 'identityChoices', 'toolValues', 'fileChoices']);
      requireValue(d.templateId === 'freeform-milling-v1' && d.millingConfirmed === true && text(d.templateReason, 1000), 'DECISIONS');
      requireValue(d.valueChoices.length <= 1200 && d.identityChoices.length <= 300 && d.toolValues.length <= 300 && d.fileChoices.length <= 100, 'DECISION_LIMIT');
      for (const choice of d.valueChoices) { keys(choice, ['rowId', 'ruleId', 'column', 'reason']); requireValue(s.orderedRowIds.includes(choice.rowId) && text(choice.ruleId) && text(choice.column) && text(choice.reason, 1000), 'VALUE_CHOICE'); }
      for (const choice of d.identityChoices) { keys(choice, ['rowId', 'configurationId', 'reason']); requireValue(s.orderedRowIds.includes(choice.rowId) && text(choice.configurationId) && text(choice.reason, 1000), 'IDENTITY_CHOICE'); }
      for (const choice of d.toolValues) {
        keys(choice, ['toolTag', 'values', 'reason']);
        requireValue(/^T\d{1,6}$/.test(choice.toolTag) && text(choice.reason, 1000) && Object.keys(choice.values).length <= 30, 'TOOL_VALUES');
        for (const value of Object.values(choice.values)) { keys(value, ['value', 'unit']); requireValue(typeof value.value === 'number' && Number.isFinite(value.value) && ['mm', 'in', '1', 'deg'].includes(value.unit), 'TOOL_VALUE'); }
      }
      for (const choice of d.fileChoices) { keys(choice, ['rowId', 'purpose', 'reason']); requireValue(rows.get(item.importEntryId)?.has(choice.rowId) && ['NC', 'STEP', 'OTHER'].includes(choice.purpose) && text(choice.reason, 1000), 'FILE_CHOICE'); }
    }
  }
  const assets = new Map(draft.assets.map(a => [a.assetNodeId, a]));
  const reach = new Map(draft.assets.map(a => [a.assetNodeId, reachableNodes(draft, a.assetNodeId)]));
  const legacyWps = new Set([...(draft.manualWorkplans ?? []), ...(draft.manualToolLinks ?? []).map(l => l.workplanNodeId), ...(draft.toolLinks ?? []).map(l => l.workplanNodeId), ...(draft.ncReviews ?? []).map(l => l.workplanNodeId)]);
  const legacySteps = new Set([...(draft.manualToolLinks ?? []).map(l => l.stepNodeId), ...(draft.toolLinks ?? []).flatMap(l => l.stepNodeIds)]);
  const wps = new Map(metadata.elsWorkplans.map(w => [w.workplanNodeId, w]));
  requireValue(unique(metadata.elsWorkplans.map(w => w.workplanNodeId)), 'WORKPLAN_IDENTITY');
  const owned = new Map<string, string>();
  for (const wp of metadata.elsWorkplans) {
    keys(wp, ['workplanNodeId', 'importEntryId', 'steps']);
    const node = draft.nodes[wp.workplanNodeId], source = imports.get(wp.importEntryId);
    requireValue(source && node?.typeId === 'Workplan' && reach.get(draft.projectAssetNodeId)?.has(wp.workplanNodeId) && !legacyWps.has(wp.workplanNodeId), 'WORKPLAN_OWNERSHIP');
    requireValue(wp.steps.length > 0 && wp.steps.length <= 300 && jsonEqual(node.fields.its_elements, wp.steps.map(s => ({ $node: s.stepNodeId }))), 'STEP_ORDER');
    requireValue(jsonEqual(wp.steps.filter(s => s.kind === 'els').map(s => s.sourceRowId), source!.selection.orderedRowIds), 'SOURCE_ORDER');
    for (const step of wp.steps) {
      keys(step, step.kind === 'els' ? ['kind', 'stepNodeId', 'sourceRowId'] : ['kind', 'stepNodeId', 'reason']);
      requireValue(!owned.has(step.stepNodeId) && !legacySteps.has(step.stepNodeId) && draft.nodes[step.stepNodeId]?.typeId === 'MachiningWorkingstep', 'STEP_OWNERSHIP');
      requireValue(step.kind === 'els' || (step.kind === 'manual' && text(step.reason, 1000)), 'STEP_SOURCE');
      owned.set(step.stepNodeId, wp.workplanNodeId);
    }
  }
  for (const node of Object.values(draft.nodes)) if (node.typeId === 'Workplan' && Array.isArray(node.fields.its_elements)) {
    for (const ref of node.fields.its_elements) if (isRef(ref) && owned.has(ref.$node)) requireValue(owned.get(ref.$node) === node.nodeId, 'STEP_OWNERSHIP');
  }
  requireValue(unique(metadata.elsToolLinks.map(l => l.stepNodeId)) && metadata.elsToolLinks.length === owned.size, 'TOOL_LINKS');
  const tags = new Map<string, string>();
  for (const link of metadata.elsToolLinks) {
    keys(link, ['workplanNodeId', 'stepNodeId', 'assetNodeId', 'toolTag', 'sourceToolNo']);
    const asset = assets.get(link.assetNodeId), wp = wps.get(link.workplanNodeId);
    requireValue(wp && owned.get(link.stepNodeId) === link.workplanNodeId && /^T\d{1,6}$/.test(link.toolTag), 'TOOL_SCOPE');
    requireValue(asset?.role === 'tool' && draft.nodes[asset.elementNodeId]?.typeId === 'DtCuttingTool13399' && draft.manualTools?.some(t => t.assetNodeId === link.assetNodeId), 'TOOL_DEFINITION');
    const tag = `${link.workplanNodeId}:${Number(link.toolTag.slice(1))}`;
    requireValue(!tags.has(tag) || tags.get(tag) === link.assetNodeId, 'TOOL_TAG_CONFLICT'); tags.set(tag, link.assetNodeId);
    const step = wp!.steps.find(s => s.stepNodeId === link.stepNodeId)!;
    if (step.kind === 'els') {
      const row = rows.get(wp!.importEntryId)!.get(step.sourceRowId)!;
      const raw = Object.entries(row.values).find(([k]) => k.toLowerCase() === 'toolno')?.[1];
      requireValue(typeof raw === 'string' && /^[Tt]?\d{1,6}$/.test(raw) && raw === link.sourceToolNo && Number(raw.replace(/^[Tt]/, '')) === Number(link.toolTag.slice(1)), 'TOOL_SOURCE');
    } else requireValue(link.sourceToolNo == null, 'MANUAL_TOOL_SOURCE');
    const op = draft.nodes[link.stepNodeId].fields.its_operation;
    requireValue(!isRef(op) || !('ref_dt_cutting_tool' in draft.nodes[op.$node].fields), 'RAW_TOOL_REFERENCE');
  }
  for (const origin of metadata.elsOrigins) {
    keys(origin, ['importEntryId', 'nodeId', 'fieldName', 'kind', 'sources', 'appliedValue', 'rule', 'reason', 'sourceUnit', 'targetUnit']);
    requireValue(imports.has(origin.importEntryId) && catalog.types[draft.nodes[origin.nodeId]?.typeId]?.fields.some(f => f.fieldName === origin.fieldName), 'ORIGIN_TARGET');
    requireValue(['source', 'derived', 'generated', 'default', 'placeholder', 'manual'].includes(origin.kind) && text(origin.rule) && text(origin.reason, 1000) && fieldValue(origin.appliedValue), 'ORIGIN_VALUE');
    requireValue(origin.sources.length <= 16 && (!['source', 'derived'].includes(origin.kind) || origin.sources.length > 0), 'ORIGIN_SOURCE');
    for (const source of origin.sources) { keys(source, ['rowId', 'column']); requireValue(Object.hasOwn(rows.get(origin.importEntryId)?.get(source.rowId)?.values ?? {}, source.column), 'ORIGIN_CELL'); }
  }
  requireValue(unique(metadata.elsReviews.map(r => r.workplanNodeId)), 'REVIEW_IDENTITY');
  for (const review of metadata.elsReviews) { keys(review, ['workplanNodeId', 'snapshotHash', 'profileHash', 'acknowledged']); requireValue(wps.has(review.workplanNodeId) && review.profileHash === profileHash && hash(review.snapshotHash) && review.acknowledged === true, 'REVIEW_SCOPE'); }
  requireValue(unique(metadata.elsFileLinks.map(l => l.assetNodeId)), 'FILE_IDENTITY');
  for (const link of metadata.elsFileLinks) {
    keys(link, ['mode', 'assetNodeId', 'projectAssetNodeId', 'workplanNodeId', 'importEntryId', 'sourceRowId', 'sourcePath', 'purpose']);
    const asset = assets.get(link.assetNodeId), row = rows.get(link.importEntryId)?.get(link.sourceRowId);
    requireValue(link.mode === 'metadata-only' && ['NC', 'STEP', 'OTHER'].includes(link.purpose) && text(link.sourcePath, 4096) && row && ['Part_File', 'Machine_File', 'Tool_File'].includes(row.table), 'FILE_SOURCE');
    requireValue(Object.entries(row!.values).find(([k]) => k.toLowerCase() === 'file_path')?.[1] === link.sourcePath, 'FILE_PATH');
    requireValue(asset?.role === 'file' && draft.nodes[asset.elementNodeId]?.typeId === 'DtFile' && !('value' in draft.nodes[asset.elementNodeId].fields) && !draft.fileLinks?.some(l => l.assetNodeId === link.assetNodeId), 'FILE_MODE');
    requireValue(link.projectAssetNodeId === draft.projectAssetNodeId && (link.workplanNodeId == null || wps.has(link.workplanNodeId)), 'FILE_SCOPE');
  }
}

export function validateWorkspaceSnapshot(record: WorkspaceSnapshot, catalog: Catalog, profileHash: string): void {
  if (record.formatVersion === 1) { validateRecovery(record, catalog); return; }
  requireValue(record.formatVersion === 2 && jsonEqual(record.requiredCapabilities, ['els-import-v1']) && 'elsMetadata' in record.data, 'RECOVERY_CAPABILITY');
  const { elsMetadata, ...legacy } = record.data;
  validateRecovery({ formatVersion: 1, sequence: record.sequence, savedAt: record.savedAt, data: legacy }, catalog);
  validateElsMetadata(record.data.draft, elsMetadata, catalog, profileHash);
}

export function workspaceFromCandidate(current: RecoverableWorkspace, candidate: ElsCandidate, sequence: number, catalog: Catalog, profileHash: string): ElsWorkspaceData {
  const base = current.draft, request = candidate.request, next = candidate.draft;
  requireValue(request.expectedSequence === sequence && request.baseDraftId === base.draftId && request.baseRevision === base.revision, 'STALE_BASE');
  requireValue(request.profileHash === profileHash && candidate.recoveryFormatVersion === 2 && jsonEqual(candidate.requiredCapabilities, ['els-import-v1']) && candidate.machineReady === false && candidate.finalizable === false && candidate.persisted === false && candidate.purpose === 'authoring-review-only', 'CANDIDATE_CONTRACT');
  requireValue(candidate.metadata.elsImports.some(i => jsonEqual(i.selection, request.selection)), 'SELECTION_MISMATCH');
  requireValue(!hasUnintegratedElsData(next), 'INLINE_METADATA');
  if (request.mode === 'replace-project') {
    requireValue(next.draftId !== base.draftId && next.revision === 0, 'REPLACEMENT_IDENTITY');
  } else {
    requireValue(request.mode === 'append-tools' && next.draftId === base.draftId && next.revision === base.revision + 1, 'APPEND_IDENTITY');
    const flexible = new Set(['revision', 'nodes', 'assets', 'manualTools']);
    for (const key of new Set([...Object.keys(base), ...Object.keys(next)])) if (!flexible.has(key)) {
      const name = key as keyof Draft;
      // Backend DTOs materialize optional empty collections on the wire.
      const collection = ['fileLinks', 'toolLinks', 'ncReviews', 'completionEntries', 'referenceLinks', 'manualToolLinks', 'manualWorkplans'].includes(key);
      const normalize = (value: unknown) => key === 'ncReviews' && Array.isArray(value) ? value.map(r => ({ ...r, manual: r.manual ?? null })) : value;
      requireValue(jsonEqual(normalize(base[name] ?? (collection ? [] : null)), normalize(next[name] ?? (collection ? [] : null))), 'APPEND_EXISTING_DATA');
    }
    for (const [id, node] of Object.entries(base.nodes)) requireValue(jsonEqual(node, next.nodes[id]), 'APPEND_EXISTING_NODE');
    const normalizeTools = (tools: NonNullable<Draft['manualTools']>) => tools.map(t => ({ ...t, legacyUnits: t.legacyUnits ?? false }));
    requireValue(jsonEqual(next.assets.slice(0, base.assets.length), base.assets) && jsonEqual(normalizeTools((next.manualTools ?? []).slice(0, base.manualTools?.length ?? 0)), normalizeTools(base.manualTools ?? [])), 'APPEND_EXISTING_ASSET');
    const added = next.assets.slice(base.assets.length), definitions = (next.manualTools ?? []).slice(base.manualTools?.length ?? 0);
    requireValue(added.length > 0 && added.every(a => a.role === 'tool' && next.nodes[a.elementNodeId]?.typeId === 'DtCuttingTool13399') && unique(added.map(a => a.assetNodeId)) && jsonEqual(added.map(a => a.assetNodeId).sort(), definitions.map(t => t.assetNodeId).sort()), 'APPEND_TOOLS_ONLY');
    const covered = new Set(added.flatMap(a => [...reachableNodes(next, a.assetNodeId)]));
    requireValue([...covered].every(id => !base.nodes[id]) && Object.keys(next.nodes).every(id => base.nodes[id] || covered.has(id)), 'APPEND_GRAPH');
    const old = 'elsMetadata' in current ? current.elsMetadata : null;
    for (const name of ['elsWorkplans', 'elsToolLinks', 'elsReviews', 'elsFileLinks'] as const) requireValue(jsonEqual(candidate.metadata[name], old?.[name] ?? []), 'APPEND_POLICY');
    for (const name of ['elsImports', 'elsOrigins'] as const) requireValue(jsonEqual(candidate.metadata[name].slice(0, old?.[name].length ?? 0), old?.[name] ?? []), 'APPEND_SOURCE');
    requireValue(candidate.metadata.elsOrigins.slice(old?.elsOrigins.length ?? 0).every(o => !base.nodes[o.nodeId]), 'APPEND_ORIGIN');
    const imports = candidate.metadata.elsImports;
    requireValue(!imports.some((item, index) => imports.slice(0, index).some(prior => prior.sourceSha256 === item.sourceSha256 && prior.profileHash === item.profileHash && jsonEqual(prior.selection, item.selection))), 'DUPLICATE_IMPORT');
  }
  const appended: Draft = { ...base, revision: next.revision,
    nodes: { ...base.nodes, ...Object.fromEntries(Object.entries(next.nodes).filter(([id]) => !base.nodes[id])) },
    assets: [...base.assets, ...next.assets.slice(base.assets.length)],
    manualTools: [...(base.manualTools ?? []), ...(next.manualTools ?? []).slice(base.manualTools?.length ?? 0)] };
  const data: ElsWorkspaceData = request.mode === 'append-tools'
    ? { ...current, draft: appended, elsMetadata: candidate.metadata }
    : { draft: next, elsMetadata: candidate.metadata, screen: 'operator', role: 'project', assetId: next.projectAssetNodeId,
      path: [], rawInputs: {}, extraFields: {}, camSessions: {}, camImports: [], ncSessions: {}, completionSettings: {}, files: {} };
  validateWorkspaceSnapshot(snapshotOf(data, sequence + 1), catalog, profileHash);
  return data;
}
