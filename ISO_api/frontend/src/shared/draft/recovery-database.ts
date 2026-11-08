export function openRecoveryDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('dt-project-creator', 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('workspace');
      request.result.createObjectStore('files');
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('다른 탭에서 로컬 저장소를 사용하고 있습니다. 다른 탭을 닫고 다시 시도해 주세요.'));
    request.onsuccess = () => { request.result.onversionchange = () => request.result.close(); resolve(request.result); };
  });
}
