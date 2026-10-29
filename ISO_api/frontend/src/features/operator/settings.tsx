import { useState } from 'react';
import { Save } from 'lucide-react';
import { defaultPreferences, preferencesKey, readPreferences, validatePreferences } from './model';
import type { Preferences } from './model';

export function SettingsPanel() {
  const [initial] = useState(() => { try { return { value: readPreferences(), error: '' }; } catch { return { value: defaultPreferences, error: '설정을 읽지 못했습니다. 기본값을 확인 후 저장해 주세요.' }; } });
  const [value, setValue] = useState<Preferences>(initial.value);
  const [message, setMessage] = useState(initial.error); const [error, setError] = useState(!!initial.error);
  return <section className="settings-panel"><h1>생성기 설정</h1><p className="source-note">새 프로젝트부터 적용 · 현재 프로젝트의 식별자는 유지됩니다.</p><label>글로벌 자산 URI 접두사<input value={value.uriPrefix} onChange={e => setValue({ ...value, uriPrefix: e.target.value })} /></label><label>새 프로젝트 기본 화면<select value={value.defaultMode} onChange={e => setValue({ ...value, defaultMode: e.target.value as Preferences['defaultMode'] })}><option value="operator">작업자 화면</option><option value="detail">상세 편집</option></select></label><button className="primary" onClick={() => { try { const next = validatePreferences(value); localStorage.setItem(preferencesKey, JSON.stringify(next)); setValue(next); setError(false); setMessage('설정을 저장했습니다.'); } catch (e) { setError(true); setMessage(e instanceof Error ? e.message : '설정을 저장하지 못했습니다.'); } }}><Save size={16} />설정 저장</button>{message && <p role={error ? 'alert' : 'status'} className={error ? 'error-text' : 'status'}>{message}</p>}</section>;
}
