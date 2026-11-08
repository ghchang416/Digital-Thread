import { useEffect, useRef, useState } from 'react';
import type { Catalog } from '../schema/types';
import type { RecoveryRecord, WorkspaceData } from './workspace';
import { validateRecovery } from './workspace';
import { migrateNcSignatures } from '../../features/files/model';
import { hasUnintegratedElsData } from '../../features/els/contracts';
import { openRecoveryDatabase as openDatabase } from './recovery-database';

export async function readRecovery(catalog: Catalog): Promise<RecoveryRecord | null> {
  const db = await openDatabase();
  const record = await new Promise<RecoveryRecord | null>((resolve, reject) => {
    const tx = db.transaction(['workspace', 'files'], 'readonly');
    let result: RecoveryRecord | null = null;
    let failure: Error | undefined;
    const request = tx.objectStore('workspace').get('active');
    request.onsuccess = () => {
      try {
        result = request.result ?? null;
        if (result) for (const [id, file] of Object.entries(result.data.files)) {
          const blob = tx.objectStore('files').get(id);
          blob.onsuccess = () => { file.blob = blob.result; };
        }
      } catch { failure = new Error('로컬 초안 형식이 손상되었습니다. 기존 데이터는 보존했습니다.'); tx.abort(); }
    };
    tx.oncomplete = () => { db.close(); resolve(result); };
    tx.onabort = () => { db.close(); reject(failure ?? tx.error ?? new Error('로컬 저장소를 읽을 수 없습니다.')); };
  });
  if (record) {
    validateRecovery(record, catalog);
    for (const file of Object.values(record.data.files)) {
      const digest = await crypto.subtle.digest('SHA-256', await file.blob.arrayBuffer());
      const hash = [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('');
      if (hash !== file.sha256) throw new Error('로컬 CAM 원본의 해시가 일치하지 않습니다. 기존 데이터는 보존했습니다.');
    }
  }
  if (record?.data.ncSessions) {
    const sessions = migrateNcSignatures(record.data.draft, record.data.ncSessions);
    if (sessions !== record.data.ncSessions) return { ...record, data: { ...record.data, ncSessions: sessions } };
  }
  return record;
}

export async function saveRecovery(data: WorkspaceData, expectedSequence: number, replaceFiles = false): Promise<RecoveryRecord> {
  if ('elsMetadata' in data || hasUnintegratedElsData(data) || hasUnintegratedElsData(data.draft)) throw new Error('ELS 초안을 기존 복구 형식으로 저장할 수 없습니다. 기존 데이터는 보존했습니다.');
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['workspace', 'files'], 'readwrite');
    let failure: Error | undefined;
    const record: RecoveryRecord = { formatVersion: 1, sequence: expectedSequence + 1, savedAt: new Date().toISOString(), data };
    const request = tx.objectStore('workspace').get('active');
    request.onsuccess = () => {
      if ((request.result?.sequence ?? 0) !== expectedSequence) {
        failure = new Error('다른 탭에서 초안이 변경되어 자동 저장을 멈췄습니다. 이 탭의 필요한 내용을 내보낸 뒤 새로고침해 주세요.');
        tx.abort(); return;
      }
      if (!replaceFiles && request.result && request.result.formatVersion !== 1) {
        failure = new Error('새 형식의 초안을 기존 저장 방식으로 덮어쓸 수 없습니다. 기존 데이터는 보존했습니다.');
        tx.abort(); return;
      }
      // Graph and file references commit together; existing blobs need not be rewritten on every edit.
      if (replaceFiles) { tx.objectStore('files').clear(); tx.objectStore('workspace').delete('previous'); }
      const metadata = Object.fromEntries(Object.entries(data.files).map(([id, file]) => {
        const { blob, ...info } = file;
        const stored = tx.objectStore('files').getKey(id);
        stored.onsuccess = () => { if (stored.result === undefined) tx.objectStore('files').put(blob, id); };
        return [id, info];
      }));
      tx.objectStore('workspace').put({ ...record, data: { ...data, files: metadata } }, 'active');
    };
    tx.oncomplete = () => { db.close(); resolve(record); };
    tx.onabort = () => { db.close(); reject(failure ?? tx.error ?? new Error('로컬 저장에 실패했습니다.')); };
  });
}

export function resetRecovery(data: WorkspaceData, expectedSequence: number): Promise<RecoveryRecord> {
  // Keep a monotonic sequence so older tabs cannot resurrect the discarded draft.
  return saveRecovery(data, expectedSequence, true);
}

export function useRecovery(data: WorkspaceData, initialSequence: number) {
  const sequence = useRef(initialSequence);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const stopped = useRef(false);
  const generation = useRef(0);
  const resetting = useRef(false);
  const [saved, setSaved] = useState<WorkspaceData | null>(initialSequence ? data : null);
  const savedRef = useRef(saved);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (savedRef.current === data) return;
    const scheduledGeneration = generation.current;
    const timer = setTimeout(() => {
      queue.current = queue.current.then(async () => {
        if (stopped.current || resetting.current || scheduledGeneration !== generation.current) return;
        try { const record = await saveRecovery(data, sequence.current); sequence.current = record.sequence; savedRef.current = data; setSaved(data); setError(''); }
        catch (e) { stopped.current = true; setError(e instanceof Error ? e.message : '로컬 저장에 실패했습니다. 브라우저 저장 공간을 확인해 주세요.'); }
      });
    }, 350);
    return () => clearTimeout(timer);
  }, [data, retry]);
  const pending = saved !== data;
  useEffect(() => {
    if (!pending) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [pending]);
  async function reset(next: WorkspaceData) {
    if (resetting.current) throw new Error('초기화가 진행 중입니다.');
    resetting.current = true;
    generation.current++;
    try {
      await queue.current;
      const record = await resetRecovery(next, sequence.current);
      sequence.current = record.sequence;
      stopped.current = true;
      return record;
    } catch (e) {
      stopped.current = true;
      resetting.current = false;
      setError(e instanceof Error ? e.message : '초기화에 실패했습니다. 기존 내용을 유지합니다.');
      throw e;
    }
  }
  return { pending, error, reset, retry: () => { if (resetting.current) return; stopped.current = false; setError(''); setRetry(value => value + 1); } };
}
