import type { VmProjectStatus } from "@/features/vm-projects/types/vm-project";

const STATUS_LABELS: Record<VmProjectStatus, string> = {
  "needs-fix": "Needs Fix",
  ready: "Ready",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

interface StatusBadgeProps {
  status: VmProjectStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${status}`}>{STATUS_LABELS[status]}</span>;
}

export function getStatusLabel(status: VmProjectStatus) {
  return STATUS_LABELS[status];
}
