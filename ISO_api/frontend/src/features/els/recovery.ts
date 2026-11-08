import type { Catalog } from '../../shared/schema/types';
import type { LocalFile } from '../cam/types';
import { openRecoveryDatabase } from '../../shared/draft/recovery-database';
import type { ElsCandidate } from './contracts';
import { snapshotOf, validateWorkspaceSnapshot, workspaceFromCandidate } from './workspace';
import type { ElsRecoveryRecord, RecoverableWorkspace, WorkspaceSnapshot } from './workspace';

export interface ElsRecoveryContext {
  catalog: Catalog;
  profileHash: string;
  signal: AbortSignal;
  // The UI coordinator must invalidate this on edits, navigation, reset or unmount,
  // serialize autosaves, and lock editing for the commit. Not wired into the UI yet.
  isCurrent: () => boolean;
}
type Slots = { active: WorkspaceSnapshot | null; previous: WorkspaceSnapshot | null };

function checkCurrent(context: ElsRecoveryContext) {
  context.signal.throwIfAborted();
  if (!context.isCurrent()) throw new Error('ELS_STALE_OPERATION: 작업 중 입력이나 선택이 변경되었습니다. 다시 준비해 주세요.');
}

async function readSlots(): Promise<Slots> {
  const db = await openRecoveryDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['workspace', 'files'], 'readonly');
    const slots: Slots = { active: null, previous: null };
    let failure: unknown;
    for (const key of ['active', 'previous'] as const) {
      const request = tx.objectStore('workspace').get(key);
      request.onsuccess = () => {
        try {
          const record = request.result as WorkspaceSnapshot | undefined;
          slots[key] = record ?? null;
          if (record) for (const [id, file] of Object.entries(record.data.files)) {
            const read = tx.objectStore('files').get(id);
            read.onsuccess = () => { file.blob = read.result; };
          }
        } catch (error) { failure = error; tx.abort(); }
      };
    }
    tx.oncomplete = () => { db.close(); resolve(slots); };
    tx.onabort = () => { db.close(); reject(failure ?? tx.error ?? new Error('로컬 초안을 읽을 수 없습니다.')); };
  });
}

async function verifyFiles(data: RecoverableWorkspace, context: ElsRecoveryContext) {
  for (const [id, file] of Object.entries(data.files)) {
    checkCurrent(context);
    if (file.fileId !== id || !(file.blob instanceof Blob) || file.size !== file.blob.size) throw new Error('ELS_FILE_MISSING: 로컬 원본 파일을 확인해 주세요.');
    const digest = await crypto.subtle.digest('SHA-256', await file.blob.arrayBuffer());
    const hash = [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
    if (hash !== file.sha256) throw new Error('ELS_FILE_HASH: 로컬 원본 파일이 변경되었습니다.');
  }
  checkCurrent(context);
}

async function validateSnapshot(record: WorkspaceSnapshot, context: ElsRecoveryContext) {
  validateWorkspaceSnapshot(record, context.catalog, context.profileHash);
  await verifyFiles(record.data, context);
}

// Opt-in reader for the future ELS-aware editor. The current app continues using
// readRecovery(), which rejects v2 rather than silently discarding provenance.
export async function readElsRecovery(context: ElsRecoveryContext): Promise<Slots> {
  checkCurrent(context);
  const slots = await readSlots();
  for (const record of [slots.active, slots.previous]) if (record) await validateSnapshot(record, context);
  checkCurrent(context);
  return slots;
}

function unionFiles(records: (WorkspaceSnapshot | null)[]): Record<string, LocalFile> {
  const files: Record<string, LocalFile> = {};
  for (const record of records) if (record) for (const [id, file] of Object.entries(record.data.files)) {
    if (files[id] && (files[id].sha256 !== file.sha256 || files[id].size !== file.size)) throw new Error('ELS_FILE_ID_CONFLICT: 같은 파일 ID의 원본 내용이 다릅니다.');
    files[id] = file;
  }
  return files;
}

function storedRecord(record: WorkspaceSnapshot): object {
  const files = Object.fromEntries(Object.entries(record.data.files).map(([id, file]) => {
    const { blob: _blob, ...info } = file;
    return [id, info];
  }));
  return { ...record, data: { ...record.data, files } };
}

function assertBase(current: RecoverableWorkspace, active: WorkspaceSnapshot | null, expectedSequence: number) {
  if (!Number.isSafeInteger(expectedSequence) || expectedSequence < 0 || (active?.sequence ?? 0) !== expectedSequence) throw new Error('ELS_STALE_SEQUENCE: 다른 탭에서 초안이 변경되었습니다.');
  if (active && (active.data.draft.draftId !== current.draft.draftId || active.data.draft.revision > current.draft.revision)) throw new Error('ELS_STALE_BASE: 현재 초안이 저장된 초안과 다릅니다.');
  if (active?.formatVersion === 2 && !('elsMetadata' in current)) throw new Error('ELS_METADATA_REQUIRED: ELS 출처를 제거한 상태로 교체할 수 없습니다.');
}

async function commit(active: WorkspaceSnapshot, previous: WorkspaceSnapshot | null, expectedSequence: number, context: ElsRecoveryContext): Promise<void> {
  checkCurrent(context);
  const files = unionFiles([active, previous]);
  const db = await openRecoveryDatabase();
  try { checkCurrent(context); } catch (error) { db.close(); throw error; }
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['workspace', 'files'], 'readwrite');
    let failure: unknown;
    const cancel = () => { failure = context.signal.reason ?? new Error('ELS 적용을 취소했습니다.'); try { tx.abort(); } catch { /* Already committed/aborted. */ } };
    context.signal.addEventListener('abort', cancel, { once: true });
    const finish = () => { context.signal.removeEventListener('abort', cancel); db.close(); };
    const read = tx.objectStore('workspace').get('active');
    read.onsuccess = () => {
      try {
        checkCurrent(context);
        if ((read.result?.sequence ?? 0) !== expectedSequence) throw new Error('ELS_STALE_SEQUENCE: 다른 탭에서 초안이 변경되어 적용하지 않았습니다.');
        // Both slots and their complete Blob union commit or roll back together.
        const blobs = tx.objectStore('files');
        blobs.clear();
        for (const [id, file] of Object.entries(files)) blobs.put(file.blob, id);
        tx.objectStore('workspace').put(storedRecord(active), 'active');
        if (previous) tx.objectStore('workspace').put(storedRecord(previous), 'previous');
        else tx.objectStore('workspace').delete('previous');
      } catch (error) { failure = error; tx.abort(); }
    };
    tx.oncomplete = () => { finish(); resolve(); };
    tx.onabort = () => { finish(); reject(failure ?? tx.error ?? new Error('로컬 저장에 실패했습니다. 이전 초안과 원본은 보존했습니다.')); };
  });
}

export async function applyElsRecovery(current: RecoverableWorkspace, candidate: ElsCandidate, expectedSequence: number,
  requestId: string, context: ElsRecoveryContext): Promise<ElsRecoveryRecord> {
  checkCurrent(context);
  // Freeze all inputs before asynchronous hashing; never save references to a mutable UI object.
  const base = structuredClone(current), prepared = structuredClone(candidate);
  if (prepared.request.requestId !== requestId) throw new Error('ELS_STALE_REQUEST: 다른 요청의 결과입니다.');
  const next = workspaceFromCandidate(base, prepared, expectedSequence, context.catalog, context.profileHash);
  const active = snapshotOf(next, expectedSequence + 1) as ElsRecoveryRecord;
  const baseSnapshot = snapshotOf(base, expectedSequence + 1);
  await validateSnapshot(baseSnapshot, context);
  await validateSnapshot(active, context);
  const stored = await readElsRecovery(context);
  assertBase(base, stored.active, expectedSequence);
  // Detect collisions even when replacement would otherwise drop the old active file.
  unionFiles([stored.active, stored.previous, baseSnapshot, active]);
  const previous = prepared.request.mode === 'replace-project' ? baseSnapshot : stored.previous;
  await commit(active, previous, expectedSequence, context);
  return active;
}

export async function restorePreviousRecovery(current: RecoverableWorkspace, expectedSequence: number,
  context: ElsRecoveryContext): Promise<WorkspaceSnapshot> {
  checkCurrent(context);
  const base = structuredClone(current), previous = snapshotOf(base, expectedSequence + 1);
  await validateSnapshot(previous, context);
  const stored = await readElsRecovery(context);
  assertBase(base, stored.active, expectedSequence);
  if (!stored.previous) throw new Error('ELS_NO_PREVIOUS: 복원할 이전 초안이 없습니다.');
  unionFiles([stored.active, stored.previous, previous]);
  const active = snapshotOf(stored.previous.data, expectedSequence + 1);
  await commit(active, previous, expectedSequence, context);
  return active;
}
