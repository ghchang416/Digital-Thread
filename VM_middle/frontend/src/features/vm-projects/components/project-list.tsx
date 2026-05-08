import { AlertCircle, Search } from "lucide-react";

import { formatDateTime } from "@/shared/lib/format";
import { getVmProjectThumbnailUrl } from "@/features/vm-projects/api/vm-projects-api";
import { StatusBadge } from "@/features/vm-projects/components/status-badge";

import type {
  VmProjectListFilters,
  VmProjectListItem,
  VmProjectStatus,
} from "@/features/vm-projects/types/vm-project";

const STATUS_OPTIONS: Array<{ value: VmProjectStatus | ""; label: string }> = [
  { value: "", label: "전체 상태" },
  { value: "needs-fix", label: "Needs Fix" },
  { value: "ready", label: "Ready" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

interface ProjectListProps {
  items: VmProjectListItem[];
  filters: VmProjectListFilters;
  selectedId: string | null;
  total: number;
  isLoading: boolean;
  errorMessage: string | null;
  onFiltersChange: (filters: VmProjectListFilters) => void;
  onSelect: (id: string) => void;
}

export function ProjectList({
  items,
  filters,
  selectedId,
  total,
  isLoading,
  errorMessage,
  onFiltersChange,
  onSelect,
}: ProjectListProps) {
  return (
    <section className="panel panel--list" aria-labelledby="vm-projects-heading">
      <div className="panel__header">
        <div>
          <h2 id="vm-projects-heading">VM Projects</h2>
          <p>생성된 VM 프로젝트와 validation 상태를 확인합니다.</p>
        </div>
        <span className="meta-count">총 {total.toLocaleString("ko-KR")}개</span>
      </div>

      <div className="filter-row" role="search">
        <label className="field field--search">
          <span className="sr-only">프로젝트 검색</span>
          <Search aria-hidden="true" size={16} />
          <input
            value={filters.q}
            placeholder="display_name, proj_name, eid"
            onChange={(event) =>
              onFiltersChange({ ...filters, q: event.target.value, page: 1 })
            }
          />
        </label>
        <label className="field">
          <span className="sr-only">상태 필터</span>
          <select
            value={filters.status}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                status: event.target.value as VmProjectStatus | "",
                page: 1,
              })
            }
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="project-list" aria-busy={isLoading}>
        {isLoading ? <ProjectListSkeleton /> : null}
        {!isLoading && errorMessage ? <ErrorState message={errorMessage} /> : null}
        {!isLoading && !errorMessage && items.length === 0 ? (
          <EmptyState />
        ) : null}
        {!isLoading && !errorMessage
          ? items.map((item) => (
              <ProjectListRow
                key={item.id}
                item={item}
                isSelected={item.id === selectedId}
                onSelect={onSelect}
              />
            ))
          : null}
      </div>
    </section>
  );
}

interface ProjectListRowProps {
  item: VmProjectListItem;
  isSelected: boolean;
  onSelect: (id: string) => void;
}

function ProjectListRow({ item, isSelected, onSelect }: ProjectListRowProps) {
  const title = item.display_name || item.proj_name || item.eid;
  const hasValidationIssue = item.validation_error_count > 0;

  return (
    <button
      type="button"
      className={`project-row ${isSelected ? "project-row--selected" : ""}`}
      onClick={() => onSelect(item.id)}
      aria-pressed={isSelected}
    >
      <span className="project-row__thumb" aria-hidden="true">
        {item.source === "dp" ? (
          <img src={getVmProjectThumbnailUrl(item.id)} alt="" loading="lazy" />
        ) : (
          <span>No image</span>
        )}
      </span>
      <span className="project-row__body">
        <span className="project-row__topline">
          <strong>{title}</strong>
          <StatusBadge status={item.status} />
        </span>
        <span className="project-row__meta">
          <span>{item.source.toUpperCase()}</span>
          <span>eid: {item.eid}</span>
          <span>wpid: {item.wpid || "-"}</span>
        </span>
        <span className="project-row__footer">
          <span className={hasValidationIssue ? "validation-pill is-warning" : "validation-pill"}>
            {hasValidationIssue ? <AlertCircle aria-hidden="true" size={13} /> : null}
            validation {item.validation_error_count}
          </span>
          <span>{formatDateTime(item.updated_at)}</span>
        </span>
      </span>
    </button>
  );
}

function ProjectListSkeleton() {
  return (
    <>
      {Array.from({ length: 6 }).map((_, index) => (
        <div className="project-row project-row--skeleton" key={index}>
          <span className="skeleton skeleton--thumb" />
          <span className="project-row__body">
            <span className="skeleton skeleton--line" />
            <span className="skeleton skeleton--line short" />
          </span>
        </div>
      ))}
    </>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="empty-state empty-state--error">
      <strong>프로젝트 목록을 불러오지 못했습니다.</strong>
      <span>{message}</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty-state">
      <strong>표시할 VM 프로젝트가 없습니다.</strong>
      <span>검색어나 상태 필터를 조정해 보세요.</span>
    </div>
  );
}
