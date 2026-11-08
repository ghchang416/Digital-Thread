import type { Draft, ManualAssignment } from '../../shared/schema/types';
import type { NcSession } from '../files/model';
import { directSteps } from '../files/model';

export const ncReasonChoices = ['NC 원문과 워킹스텝 순서를 확인함', 'T 번호와 사용 공구 연결을 확인함', '워킹스텝별 NC 시작·끝 행을 확인함'];

export function toggleNcReason(reason: string, choice: string, checked: boolean): string {
  const lines = reason.split('\n').filter(line => line.trim() !== choice);
  if (checked) lines.push(choice);
  return lines.join('\n').trim();
}

export function manualNcBlockers(draft: Draft, wpId: string, session: NcSession,
  state: { profileReady: boolean; busy: boolean; rawErrors: boolean; acknowledged: boolean }): string[] {
  const blockers: string[] = [];
  if (state.busy) blockers.push('NC 처리 중입니다.');
  if (!state.profileReady) blockers.push('공구 입력 규칙을 불러와야 합니다.');
  if (state.rawErrors) blockers.push('편집 중인 숫자 형식 오류를 수정해 주세요.');
  const steps = directSteps(draft, wpId);
  if (!steps.length) blockers.push('이 워크플랜에 워킹스텝을 추가해 주세요.');
  steps.forEach((id, index) => {
    const row: ManualAssignment | undefined = session.manualRows?.[id];
    const missing: string[] = [];
    if (!row || !/^[Tt][0-9]{1,6}$/.test(row.toolTag)) missing.push('T 번호');
    if (!row || !Number.isInteger(row.lineStart) || row.lineStart < 1 || !Number.isInteger(row.lineEnd) || row.lineEnd < row.lineStart) missing.push('시작·끝 행');
    if (!draft.manualToolLinks?.some(l => l.workplanNodeId === wpId && l.stepNodeId === id && draft.assets.some(a => a.assetNodeId === l.assetNodeId))) missing.push('공구 연결');
    if (missing.length) blockers.push(`${index + 1}. ${String(draft.nodes[id]?.fields.its_id || '워킹스텝')}: ${missing.join(', ')} 확인 필요`);
  });
  if (!session.manualReason?.trim()) blockers.push('확인 근거를 선택하거나 사유를 직접 입력해 주세요.');
  if ((session.manualReason?.length ?? 0) > 1000) blockers.push('확인 사유는 1,000자 이내로 입력해 주세요.');
  if (!state.acknowledged) blockers.push('마지막 확인 체크박스를 선택해 주세요.');
  return blockers;
}
