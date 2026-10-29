import { strToU8, zip } from 'fflate';
import type { AssetDraft, Draft, Issue, Preview } from '../../shared/schema/types';
import type { WorkspaceData } from '../../shared/draft/workspace';
import { directSteps, ncSignature } from '../files/model';
import { activeRawErrors } from '../../shared/draft/review-state';

export interface AssetResult {
  asset: AssetDraft; label: string; filename: string; result?: Preview; error?: string;
  identity: { globalAssetId: string; assetId: string; elementId: string };
  linked: boolean;
}
export interface ExportReview {
  draftId: string; revision: number; schemaHash: string; createdAt: string;
  assets: AssetResult[]; workflowIssues: Issue[];
  ncConfirmations?: Draft['ncReviews'];
}
export function isCurrent(review: ExportReview | null, data: WorkspaceData): review is ExportReview {
  return !!review && review.draftId === data.draft.draftId && review.revision === data.draft.revision
    && review.schemaHash === data.draft.schemaHash && !activeRawErrors(data.draft, data.rawInputs).length
    && JSON.stringify(review.workflowIssues) === JSON.stringify(workflowIssues(data));
}
export function workflowIssues(data: WorkspaceData): Issue[] {
  const issues: Issue[] = [];
  const add = (nodeId: string, code: string, message: string) => issues.push({ nodeId, code, message, fieldName: null, itemId: null });
  for (const node of Object.values(data.draft.nodes)) {
    if (node.typeId !== 'Workplan' || !directSteps(data.draft, node.nodeId).length) continue;
    const session = data.ncSessions?.[node.nodeId];
    if (!session?.appliedSignature || session.appliedSignature !== ncSignature(data.draft, node.nodeId, session)) {
      add(node.nodeId, 'NC_CONFIRMATION_REQUIRED', 'NC 구간·T 번호·공구 연결을 확인해 주세요.');
    }
  }
  for (const link of data.draft.fileLinks ?? []) {
    const file = data.files[link.fileId];
    if (!file || file.sha256 !== link.sha256 || file.blob.size !== file.size) add(link.assetNodeId, 'LOCAL_FILE_MISSING', '등록된 파일 원본 또는 해시를 확인해 주세요.');
  }
  const identities = new Set<string>();
  for (const asset of data.draft.assets) {
    const fields = data.draft.nodes[asset.assetNodeId]?.fields;
    const element = data.draft.nodes[asset.elementNodeId]?.fields;
    // Existing 13399 tools share an asset ID, with T1/T2/... identifying distinct elements.
    const key = JSON.stringify([String(fields?.asset_global_id ?? '').trim().replace(/\/$/, ''), String(fields?.id ?? '').trim(), String(element?.element_id ?? '').trim()]);
    if (identities.has(key)) add(asset.assetNodeId, 'DUPLICATE_ASSET_ID', '글로벌 자산 ID·자산 ID·요소 ID 조합이 중복됩니다.');
    identities.add(key);
  }
  return issues;
}
export function artifactFor(asset: AssetResult) {
  const matches = asset.result?.artifacts.filter(item => item.assetNodeId === asset.asset.assetNodeId) ?? [];
  return matches.length === 1 && matches[0].xml.trim() ? matches[0] : undefined;
}
export function exportCounts(review: ExportReview) {
  const unique = (issues: Issue[]) => new Set(issues.map(i => JSON.stringify([i.nodeId, i.fieldName, i.itemId, i.code, i.message]))).size;
  return {
    total: review.assets.length,
    generated: review.assets.filter(asset => artifactFor(asset)).length,
    errors: review.workflowIssues.length + review.assets.reduce((n, a) => n + (a.error ? 1 : 0) + (a.result?.issues.length ?? 0), 0),
    warnings: unique(review.assets.flatMap(a => a.result?.warnings ?? [])),
    pending: unique(review.assets.flatMap(a => a.result?.pendingStorage ?? [])),
  };
}
export async function generateReview(data: WorkspaceData, reviewAsset: (draft: Draft, id: string, signal: AbortSignal) => Promise<Preview>, signal: AbortSignal, progress: (count: number) => void): Promise<ExportReview> {
  if (activeRawErrors(data.draft, data.rawInputs).length) throw new Error('숫자 형식을 먼저 수정해 주세요.');
  const draft = structuredClone(data.draft);
  const output: ExportReview = { draftId: draft.draftId, revision: draft.revision, schemaHash: draft.schemaHash, createdAt: new Date().toISOString(), assets: [], workflowIssues: workflowIssues(data), ncConfirmations: draft.ncReviews };
  // Each request uses the same immutable snapshot; a failed asset must not hide the others.
  for (const [index, asset] of draft.assets.entries()) {
    signal.throwIfAborted();
    const fields = draft.nodes[asset.elementNodeId]?.fields ?? {};
    const root = draft.nodes[asset.assetNodeId]?.fields ?? {};
    const row: AssetResult = { asset, label: `${asset.role === 'tool' ? String(fields.element_id ?? '') + ' · ' : ''}${String(fields.display_name || fields.its_id || fields.element_id || asset.role)}`, filename: `xml/${String(index + 1).padStart(3, '0')}-${asset.role}.xml`,
      linked: asset.role === 'project' || !!draft.referenceLinks?.some(link => link.targetAssetNodeId === asset.assetNodeId) || !!draft.fileLinks?.some(link => link.assetNodeId === asset.assetNodeId) || !!draft.toolLinks?.some(link => link.assetNodeId === asset.assetNodeId && link.stepNodeIds.some(id => draft.nodes[id])),
      identity: { globalAssetId: String(root.asset_global_id ?? ''), assetId: String(root.id ?? ''), elementId: String(fields.element_id ?? '') } };
    try {
      row.result = await reviewAsset(draft, asset.assetNodeId, signal);
      if (!artifactFor(row) && !row.result.issues.length) row.error = '서버 응답에 대상 XML이 없습니다.';
    } catch (error) {
      signal.throwIfAborted();
      row.error = error instanceof Error ? error.message : 'XML 생성 요청 실패';
    }
    output.assets.push(row); progress(index + 1);
  }
  signal.throwIfAborted();
  return output;
}
export function exportDocuments(review: ExportReview) {
  const counts = exportCounts(review);
  const complete = counts.total > 0 && counts.generated === counts.total;
  return {
    manifest: { formatVersion: 1, purpose: 'authoring-review-only', persisted: false, finalizable: false, machineReady: false,
      draftId: review.draftId, revision: review.revision, schemaHash: review.schemaHash, createdAt: review.createdAt,
      complete, ...counts, assets: review.assets.map(row => ({ ...row.asset, ...row.identity, linked: row.linked, label: row.label, filename: artifactFor(row) ? row.filename : null, generated: !!artifactFor(row) })) },
    report: { validationScope: 'model-metadata-and-local-workflow', isoConformanceCertified: false, externalReferencesVerified: false,
      workflowIssues: review.workflowIssues, ncConfirmations: review.ncConfirmations ?? [], assets: review.assets.map(row => ({ assetNodeId: row.asset.assetNodeId, error: row.error ?? null,
        issues: row.result?.issues ?? [], warnings: row.result?.warnings ?? [], pendingStorage: row.result?.pendingStorage ?? [], omittedFields: artifactFor(row)?.omittedFields ?? [] })) },
  };
}
export function createZip(review: ExportReview): Promise<Uint8Array> {
  const documents = exportDocuments(review);
  if (!documents.manifest.complete) return Promise.reject(new Error('모든 자산의 XML을 생성한 후 다운로드할 수 있습니다.'));
  if (documents.manifest.errors) return Promise.reject(new Error('NC 연결과 XML 검증 오류를 해결한 후 다운로드할 수 있습니다.'));
  const entries: Record<string, Uint8Array> = {
    'manifest.json': strToU8(JSON.stringify(documents.manifest, null, 2)),
    'validation-report.json': strToU8(JSON.stringify(documents.report, null, 2)),
  };
  for (const row of review.assets) entries[row.filename] = strToU8(artifactFor(row)!.xml);
  return new Promise((resolve, reject) => zip(entries, { level: 6 }, (error, bytes) => error ? reject(error) : resolve(bytes)));
}
export function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
