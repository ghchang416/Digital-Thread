import { ArrowRight } from 'lucide-react';
import { groupIssues } from '../../features/completion/model';
import type { Draft, Issue } from '../schema/types';
import type { StructureRow } from '../draft/structure';

export function GroupedIssues({ issues, rows, draft, openIssue, warning = false }: { issues: Issue[]; rows: StructureRow[]; draft: Draft; openIssue: (id: string, field: string | null) => void; warning?: boolean }) {
  return <div className={`grouped-issues ${warning ? 'review-warnings' : ''}`}>{groupIssues(issues, rows, draft).map(group => <details key={group.key}>
    <summary>{group.title}<span>{group.issues.length}개 {warning ? '보완 이력' : '확인 필요'}</span></summary>
    <ul className="issues">{group.issues.map((issue, index) => <li key={index}><button disabled={!issue.nodeId || !rows.some(row => row.nodeId === issue.nodeId)} onClick={() => issue.nodeId && openIssue(issue.nodeId, issue.fieldName)}><span><small>{issue.context}</small><strong>{issue.fieldName ?? '자산'}</strong>{issue.message}</span><ArrowRight size={15} /></button></li>)}</ul>
  </details>)}</div>;
}
