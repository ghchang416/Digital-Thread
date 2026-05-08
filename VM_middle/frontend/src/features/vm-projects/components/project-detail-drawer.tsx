import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  HelpCircle,
  Play,
  RefreshCw,
  RotateCcw,
  X,
} from "lucide-react";

import { compactText, formatDateTime } from "@/shared/lib/format";
import {
  getStockItems,
  patchVmProjectProcess,
  patchVmProjectStock,
  pollVmProject,
  resetVmProject,
  startVmProject,
} from "@/features/vm-projects/api/vm-projects-api";
import { StatusBadge } from "@/features/vm-projects/components/status-badge";

import type {
  ProcessAnnotationItem,
  ProcessPatchPayload,
  ProjectFileProcess,
  StartVmPayload,
  StockPatchPayload,
  VmProjectDetail,
  VmUploadMode,
} from "@/features/vm-projects/types/vm-project";

interface ProjectDetailDrawerProps {
  detail: VmProjectDetail | null;
  annotations: ProcessAnnotationItem[];
  isOpen: boolean;
  isLoading: boolean;
  errorMessage: string | null;
  onClose: () => void;
}

export function ProjectDetailDrawer({
  detail,
  annotations,
  isOpen,
  isLoading,
  errorMessage,
  onClose,
}: ProjectDetailDrawerProps) {
  return (
    <div className={`drawer ${isOpen ? "drawer--open" : ""}`} aria-hidden={!isOpen}>
      <button
        type="button"
        className="drawer__backdrop"
        aria-label="상세 패널 닫기"
        onClick={onClose}
      />
      <aside className="drawer__panel" aria-label="VM 프로젝트 상세">
        <div className="drawer__header">
          <div>
            <h2>Project Detail</h2>
            <p>선택한 VM 프로젝트의 상태와 생성된 `project.prj` 초안을 확인합니다.</p>
          </div>
          <button className="icon-button" type="button" aria-label="닫기" onClick={onClose}>
            <X aria-hidden="true" size={18} />
          </button>
        </div>

        <div className="drawer__body">
          {isLoading ? <DetailSkeleton /> : null}
          {!isLoading && errorMessage ? (
            <div className="empty-state empty-state--error">
              <strong>상세 정보를 불러오지 못했습니다.</strong>
              <span>{errorMessage}</span>
            </div>
          ) : null}
          {!isLoading && !errorMessage && detail ? (
            <DetailContent detail={detail} annotations={annotations} />
          ) : null}
          {!isLoading && !errorMessage && !detail ? (
            <div className="empty-state">
              <strong>프로젝트를 선택해 주세요.</strong>
              <span>목록에서 프로젝트를 선택하면 상세 정보가 표시됩니다.</span>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

interface DetailContentProps {
  detail: VmProjectDetail;
  annotations: ProcessAnnotationItem[];
}

function DetailContent({ detail, annotations }: DetailContentProps) {
  const draft = detail.project_file_draft;
  const validationGroups = useMemo(
    () => groupValidationErrors(detail.validation_errors),
    [detail.validation_errors],
  );

  return (
    <div className="detail-stack">
      <div className="detail-hero">
        <div>
          <h3>{detail.display_name || detail.proj_name || detail.eid}</h3>
          <p>{detail.source.toUpperCase()} / {detail.wpid || "workplan 없음"}</p>
        </div>
        <StatusBadge status={detail.status} />
      </div>

      <div className="detail-command-strip" aria-label="VM project workbench summary">
        <MetaItem label="validation" value={`${detail.validation_errors.length} issues`} />
        <MetaItem label="process" value={`${draft.process_count} steps`} />
        <MetaItem label="stock" value={draft.stock_size} />
      </div>

      <section className="detail-section" aria-labelledby="metadata-heading">
        <SectionHeader
          id="metadata-heading"
          title="Source Metadata"
          eyebrow="Project identity"
        />
        <div className="meta-grid">
          <MetaItem label="gid" value={detail.gid} />
          <MetaItem label="aid" value={detail.aid} />
          <MetaItem label="eid" value={detail.eid} />
          <MetaItem label="wpid" value={detail.wpid} />
          <MetaItem label="created" value={formatDateTime(detail.created_at)} />
          <MetaItem label="updated" value={formatDateTime(detail.updated_at)} />
        </div>
      </section>

      <section className="detail-section" aria-labelledby="validation-heading">
        <SectionHeader
          id="validation-heading"
          title="Validation & VM Status"
          eyebrow="Readiness"
        />
        <ValidationPanel groups={validationGroups} />
        <div className="meta-grid">
          <MetaItem label="upload_mode" value={detail.upload_mode} />
          <MetaItem label="vm_job_id" value={detail.vm_job_id} />
          <MetaItem label="vm_raw_status" value={detail.vm_raw_status} />
          <MetaItem label="last_polled" value={formatDateTime(detail.vm_last_polled_at)} />
          <MetaItem label="vm_error" value={detail.vm_error_message} />
          <MetaItem
            label="uploaded"
            value={
              detail.vm_result_upload
                ? `${detail.vm_result_upload.uploaded_indices.length} / ${detail.vm_result_upload.total_count}`
                : "-"
            }
          />
        </div>
      </section>

      <section className="detail-section" aria-labelledby="execution-heading">
        <SectionHeader id="execution-heading" title="VM Execution" eyebrow="Run control" />
        <VmExecutionPanel detail={detail} />
      </section>

      <section className="detail-section" aria-labelledby="stock-heading">
        <SectionHeader
          id="stock-heading"
          title="Stock"
          eyebrow="Material bounds & alignment"
        />
        <StockEditor detail={detail} />
      </section>

      <section className="detail-section" aria-labelledby="process-heading">
        <SectionHeader
          id="process-heading"
          title="Process"
          eyebrow="NC path & tool data"
        />
        <ProcessEditor
          detail={detail}
          annotations={annotations}
          processErrors={validationGroups.process}
        />
      </section>
    </div>
  );
}

function SectionHeader({
  id,
  title,
  eyebrow,
}: {
  id: string;
  title: string;
  eyebrow: string;
}) {
  return (
    <div className="detail-section__header">
      <div>
        <span>{eyebrow}</span>
        <h4 id={id}>{title}</h4>
      </div>
    </div>
  );
}

interface ValidationGroups {
  stock: string[];
  process: string[];
  vm: string[];
  other: string[];
}

function groupValidationErrors(errors: string[]): ValidationGroups {
  return errors.reduce<ValidationGroups>(
    (groups, error) => {
      const normalized = error.toLowerCase();
      if (normalized.includes("stock_") || normalized.includes("stock ")) {
        groups.stock.push(error);
      } else if (normalized.includes("process") || normalized.includes("tool_data")) {
        groups.process.push(error);
      } else if (normalized.includes("vm_") || normalized.includes("upload")) {
        groups.vm.push(error);
      } else {
        groups.other.push(error);
      }
      return groups;
    },
    { stock: [], process: [], vm: [], other: [] },
  );
}

function ValidationPanel({ groups }: { groups: ValidationGroups }) {
  const total =
    groups.stock.length + groups.process.length + groups.vm.length + groups.other.length;

  if (total === 0) {
    return (
      <div className="validation-panel validation-panel--ok">
        <CheckCircle2 aria-hidden="true" size={18} />
        <div>
          <strong>validation error가 없습니다.</strong>
          <span>현재 project.prj 초안은 VM 실행 조건을 만족합니다.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="validation-panel validation-panel--warning">
      <div className="validation-panel__summary">
        <AlertCircle aria-hidden="true" size={18} />
        <div>
          <strong>수정이 필요한 항목 {total}개</strong>
          <span>Stock과 Process 항목을 먼저 확인하세요.</span>
        </div>
      </div>
      <div className="validation-chips" aria-label="validation error summary">
        <span>Stock {groups.stock.length}</span>
        <span>Process {groups.process.length}</span>
        <span>VM {groups.vm.length}</span>
        <span>Other {groups.other.length}</span>
      </div>
      <ValidationErrorGroup title="Stock" errors={groups.stock} />
      <ValidationErrorGroup title="Process" errors={groups.process} />
      <ValidationErrorGroup title="VM" errors={groups.vm} />
      <ValidationErrorGroup title="Other" errors={groups.other} />
    </div>
  );
}

function ValidationErrorGroup({ title, errors }: { title: string; errors: string[] }) {
  if (errors.length === 0) return null;

  return (
    <div className="validation-error-group">
      <strong>{title}</strong>
      <ul className="validation-list">
        {errors.map((error) => (
          <li key={error}>{error}</li>
        ))}
      </ul>
    </div>
  );
}

const STOCK_SIZE_AXES = [
  { axis: "X", minKey: "xMin", maxKey: "xMax", minLabel: "x_min", maxLabel: "x_max" },
  { axis: "Y", minKey: "yMin", maxKey: "yMax", minLabel: "y_min", maxLabel: "y_max" },
  { axis: "Z", minKey: "zMin", maxKey: "zMax", minLabel: "z_min", maxLabel: "z_max" },
] as const;

type StockSizeKey = (typeof STOCK_SIZE_AXES)[number]["minKey" | "maxKey"];
type StockSizeFields = Record<StockSizeKey, string>;

function StockEditor({ detail }: { detail: VmProjectDetail }) {
  const queryClient = useQueryClient();
  const draft = detail.project_file_draft;
  const [stockType, setStockType] = useState(draft.stock_type ?? "");
  const [stockSizeFields, setStockSizeFields] = useState<StockSizeFields>(() =>
    parseStockSize(draft.stock_size),
  );

  useEffect(() => {
    setStockType(draft.stock_type ?? "");
    setStockSizeFields(parseStockSize(draft.stock_size));
  }, [detail.id, draft.stock_size, draft.stock_type]);

  const stocksQuery = useQuery({
    queryKey: ["vm-project", "stocks"],
    queryFn: () => getStockItems(),
    staleTime: 1000 * 60 * 10,
  });

  const stockMutation = useMutation({
    mutationFn: (payload: StockPatchPayload) => patchVmProjectStock(detail.id, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["vm-project", detail.id] }),
        queryClient.invalidateQueries({ queryKey: ["vm-projects"] }),
      ]);
    },
  });

  const isEditable = detail.status === "ready" || detail.status === "needs-fix";
  const stockSizeCsv = serializeStockSize(stockSizeFields);
  const stockSizeError = getStockSizeError(stockSizeFields);
  const hasChanges =
    normalizeNullableText(stockType) !== normalizeNullableText(draft.stock_type) ||
    stockSizeCsv !== serializeStockSize(parseStockSize(draft.stock_size));
  const canSave = isEditable && hasChanges && !stockSizeError && !stockMutation.isPending;

  return (
    <div className="stock-workbench">
      <form
        className="stock-editor"
        onSubmit={(event) => {
          event.preventDefault();
          if (!canSave) return;
          stockMutation.mutate({
            stock_type: stockType.trim() || undefined,
            stock_size: stockSizeCsv,
          });
        }}
      >
        <div className="form-grid">
          <label className="form-field">
            <span>stock_type</span>
            <input
              list="stock-type-options"
              value={stockType}
              disabled={!isEditable}
              placeholder="예: 9"
              onChange={(event) => setStockType(event.target.value)}
            />
          </label>
          <MetaItem label="process_count" value={String(draft.process_count)} />
        </div>

        <div className="stock-size-editor" role="group" aria-labelledby="stock-size-heading">
          <div className="stock-size-editor__topline">
            <span id="stock-size-heading">stock_size</span>
            <code>{stockSizeCsv}</code>
          </div>
          <div className="stock-size-grid">
            {STOCK_SIZE_AXES.map((axis) => (
              <div
                className="axis-group"
                role="group"
                aria-label={`${axis.axis} axis`}
                key={axis.axis}
              >
                <strong>{axis.axis}</strong>
                <label className="form-field">
                  <span>{axis.minLabel}</span>
                  <input
                    aria-invalid={Boolean(stockSizeError)}
                    disabled={!isEditable}
                    inputMode="decimal"
                    placeholder="min"
                    value={stockSizeFields[axis.minKey]}
                    onChange={(event) =>
                      setStockSizeFields((fields) => ({
                        ...fields,
                        [axis.minKey]: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="form-field">
                  <span>{axis.maxLabel}</span>
                  <input
                    aria-invalid={Boolean(stockSizeError)}
                    disabled={!isEditable}
                    inputMode="decimal"
                    placeholder="max"
                    value={stockSizeFields[axis.maxKey]}
                    onChange={(event) =>
                      setStockSizeFields((fields) => ({
                        ...fields,
                        [axis.maxKey]: event.target.value,
                      }))
                    }
                  />
                </label>
              </div>
            ))}
          </div>
        </div>

        {stockSizeError ? <div className="field-error">{stockSizeError}</div> : null}

        <datalist id="stock-type-options">
          {(stocksQuery.data?.items ?? []).map((item) => (
            <option key={item.code} value={item.code}>
              {item.name}
            </option>
          ))}
        </datalist>

        {!isEditable ? (
          <div className="inline-note">
            Stock 수정은 ready 또는 needs-fix 상태에서만 가능합니다.
          </div>
        ) : null}
        {stockMutation.error instanceof Error ? (
          <div className="empty-state empty-state--error">
            <strong>Stock 저장 실패</strong>
            <span>{stockMutation.error.message}</span>
          </div>
        ) : null}
        {stockMutation.isSuccess ? (
          <div className="inline-note inline-note--success">
            Stock 정보를 저장했고 validation 상태를 다시 계산했습니다.
          </div>
        ) : null}

        <div className="form-actions">
          <button
            className="button"
            type="button"
            disabled={!hasChanges || stockMutation.isPending}
            onClick={() => {
              setStockType(draft.stock_type ?? "");
              setStockSizeFields(parseStockSize(draft.stock_size));
              stockMutation.reset();
            }}
          >
            되돌리기
          </button>
          <button className="button button--primary" type="submit" disabled={!canSave}>
            {stockMutation.isPending ? "저장 중..." : "Stock 저장"}
          </button>
        </div>
      </form>

      <StockToolpathPreview
        stockSizeFields={stockSizeFields}
        processCount={draft.process_count}
      />
    </div>
  );
}

function StockToolpathPreview({
  stockSizeFields,
  processCount,
}: {
  stockSizeFields: StockSizeFields;
  processCount: number;
}) {
  const metrics = getStockBoxMetrics(stockSizeFields);

  return (
    <aside className="stock-preview" aria-label="Toolpath and stock alignment preview">
      <div className="stock-preview__header">
        <div>
          <span>NC overlay</span>
          <strong>Toolpath Alignment</strong>
        </div>
        <span className="preview-badge">screen only</span>
      </div>

      <div className="stock-preview__canvas" aria-hidden="true">
        <svg viewBox="0 0 420 260" role="img">
          <defs>
            <pattern id="stock-grid" width="24" height="24" patternUnits="userSpaceOnUse">
              <path d="M 24 0 L 0 0 0 24" />
            </pattern>
          </defs>
          <rect className="stock-preview__grid" x="0" y="0" width="420" height="260" />
          <g className="stock-preview__box">
            <polygon points="96,82 302,82 352,122 146,122" />
            <polygon points="146,122 352,122 352,198 146,198" />
            <polygon points="96,82 146,122 146,198 96,158" />
            <polyline points="96,82 302,82 352,122 352,198 146,198 96,158 96,82" />
            <line x1="302" y1="82" x2="302" y2="158" />
            <line x1="302" y1="158" x2="352" y2="198" />
          </g>
          <path
            className="stock-preview__toolpath stock-preview__toolpath--shadow"
            d="M 82 182 C 118 143, 152 145, 184 165 S 240 187, 264 135 S 322 74, 354 104"
          />
          <path
            className="stock-preview__toolpath"
            d="M 82 176 C 118 137, 152 139, 184 159 S 240 181, 264 129 S 322 68, 354 98"
          />
          <circle cx="82" cy="176" r="5" className="stock-preview__node" />
          <circle cx="354" cy="98" r="5" className="stock-preview__node" />
        </svg>
      </div>

      <div className="stock-preview__metrics">
        <MetaItem label="x_span" value={metrics.xSpan} />
        <MetaItem label="y_span" value={metrics.ySpan} />
        <MetaItem label="z_span" value={metrics.zSpan} />
        <MetaItem label="nc_steps" value={String(processCount)} />
      </div>
    </aside>
  );
}

function getStockBoxMetrics(fields: StockSizeFields) {
  return {
    xSpan: formatAxisSpan(fields.xMin, fields.xMax),
    ySpan: formatAxisSpan(fields.yMin, fields.yMax),
    zSpan: formatAxisSpan(fields.zMin, fields.zMax),
  };
}

function formatAxisSpan(minValue: string, maxValue: string) {
  const min = Number(minValue);
  const max = Number(maxValue);
  if (Number.isNaN(min) || Number.isNaN(max)) return "-";
  return `${formatMetricValue(max - min)} mm`;
}

function formatMetricValue(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function parseStockSize(value: string | null | undefined): StockSizeFields {
  const [xMin = "", xMax = "", yMin = "", yMax = "", zMin = "", zMax = ""] =
    (value ?? "").split(",").map((part) => part.trim());

  return { xMin, xMax, yMin, yMax, zMin, zMax };
}

function serializeStockSize(fields: StockSizeFields) {
  return [
    fields.xMin,
    fields.xMax,
    fields.yMin,
    fields.yMax,
    fields.zMin,
    fields.zMax,
  ]
    .map((value) => value.trim())
    .join(",");
}

function getStockSizeError(fields: StockSizeFields) {
  const values = Object.values(fields).map((value) => value.trim());
  if (values.every((value) => value === "")) {
    return "Stock size는 X/Y/Z min/max 6개 값을 모두 입력해야 합니다.";
  }
  if (values.some((value) => value === "")) {
    return "Stock size에 비어 있는 축 값이 있습니다.";
  }
  if (values.some((value) => Number.isNaN(Number(value)))) {
    return "Stock size는 숫자만 입력할 수 있습니다.";
  }

  for (const axis of STOCK_SIZE_AXES) {
    if (Number(fields[axis.minKey]) > Number(fields[axis.maxKey])) {
      return `${axis.axis}축 min 값은 max 값보다 클 수 없습니다.`;
    }
  }

  return null;
}

const UPLOAD_MODE_OPTIONS: Array<{
  value: VmUploadMode;
  label: string;
  description: string;
}> = [
  {
    value: "file",
    label: "File",
    description: "결과 ZIP을 다운로드해 DP에 파일로 등록합니다.",
  },
  {
    value: "link",
    label: "Link",
    description: "결과 ZIP 링크만 dt_file path에 등록합니다.",
  },
  {
    value: "json",
    label: "JSON",
    description: "workingstep별 JSON 결과를 개별 dt_file로 등록합니다.",
  },
];

function VmExecutionPanel({ detail }: { detail: VmProjectDetail }) {
  const queryClient = useQueryClient();
  const [uploadMode, setUploadMode] = useState<VmUploadMode>(
    normalizeUploadMode(detail.upload_mode),
  );

  useEffect(() => {
    setUploadMode(normalizeUploadMode(detail.upload_mode));
  }, [detail.id, detail.upload_mode]);

  const startMutation = useMutation({
    mutationFn: (payload: StartVmPayload) => startVmProject(detail.id, payload),
    onSuccess: async () => {
      await refreshVmProjectQueries(queryClient, detail.id);
    },
  });

  const pollMutation = useMutation({
    mutationFn: () => pollVmProject(detail.id),
    onSuccess: async () => {
      await refreshVmProjectQueries(queryClient, detail.id);
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => resetVmProject(detail.id),
    onSuccess: async () => {
      await refreshVmProjectQueries(queryClient, detail.id);
    },
  });

  const canStart = detail.status === "ready" && !detail.vm_job_id;
  const canPoll = detail.status === "running" && Boolean(detail.vm_job_id);
  const canReset = detail.status === "failed";
  const disabledReason = getVmStartDisabledReason(detail);
  const isActionPending =
    startMutation.isPending || pollMutation.isPending || resetMutation.isPending;

  return (
    <div className="execution-panel">
      <div className="execution-panel__status">
        <div>
          <strong>{canStart ? "VM 실행 준비 완료" : "VM 실행 대기"}</strong>
          <span>{disabledReason ?? "upload mode를 선택한 뒤 VM 작업을 시작할 수 있습니다."}</span>
        </div>
        <StatusBadge status={detail.status} />
      </div>

      <fieldset className="mode-options" disabled={!canStart || startMutation.isPending}>
        <legend>upload_mode</legend>
        {UPLOAD_MODE_OPTIONS.map((option) => (
          <label
            className={`mode-option ${uploadMode === option.value ? "mode-option--selected" : ""}`}
            key={option.value}
          >
            <input
              type="radio"
              name={`upload-mode-${detail.id}`}
              value={option.value}
              checked={uploadMode === option.value}
              onChange={() => setUploadMode(option.value)}
            />
            <span>
              <strong>{option.label}</strong>
              <small>{option.description}</small>
            </span>
          </label>
        ))}
      </fieldset>

      {uploadMode === "json" ? (
        <div className="inline-note inline-note--warning">
          JSON 모드는 중간 실패 시 일부 dt_file이 이미 등록될 수 있습니다. 실행 전
          validation과 process 매핑을 확인하세요.
        </div>
      ) : null}
      {startMutation.error instanceof Error ? (
        <div className="empty-state empty-state--error">
          <strong>VM 실행 시작 실패</strong>
          <span>{startMutation.error.message}</span>
        </div>
      ) : null}
      {pollMutation.error instanceof Error ? (
        <div className="empty-state empty-state--error">
          <strong>VM 상태 조회 실패</strong>
          <span>{pollMutation.error.message}</span>
        </div>
      ) : null}
      {resetMutation.error instanceof Error ? (
        <div className="empty-state empty-state--error">
          <strong>VM 프로젝트 리셋 실패</strong>
          <span>{resetMutation.error.message}</span>
        </div>
      ) : null}
      {startMutation.isSuccess ? (
        <div className="inline-note inline-note--success">
          VM 작업을 시작했습니다. 목록과 상세 상태를 갱신합니다.
        </div>
      ) : null}
      {pollMutation.isSuccess ? (
        <div className="inline-note inline-note--success">
          VM 상태를 조회했습니다. 최신 상태를 다시 불러옵니다.
        </div>
      ) : null}
      {resetMutation.isSuccess ? (
        <div className="inline-note inline-note--success">
          failed 프로젝트를 ready 상태로 리셋했습니다.
        </div>
      ) : null}

      <div className="form-actions">
        <button
          className="button"
          type="button"
          disabled={!canPoll || isActionPending}
          onClick={() => pollMutation.mutate()}
        >
          <RefreshCw aria-hidden="true" size={15} />
          {pollMutation.isPending ? "조회 중..." : "Poll Now"}
        </button>
        <button
          className="button"
          type="button"
          disabled={!canReset || isActionPending}
          onClick={() => resetMutation.mutate()}
        >
          <RotateCcw aria-hidden="true" size={15} />
          {resetMutation.isPending ? "리셋 중..." : "Reset to Ready"}
        </button>
        <button
          className="button button--primary"
          type="button"
          disabled={!canStart || isActionPending}
          onClick={() => startMutation.mutate({ upload_mode: uploadMode })}
        >
          <Play aria-hidden="true" size={15} />
          {startMutation.isPending ? "VM 시작 중..." : "Start VM"}
        </button>
      </div>
    </div>
  );
}

async function refreshVmProjectQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["vm-project", id] }),
    queryClient.invalidateQueries({ queryKey: ["vm-projects"] }),
  ]);
}

function normalizeUploadMode(value: string | null): VmUploadMode {
  return value === "link" || value === "json" ? value : "file";
}

function getVmStartDisabledReason(detail: VmProjectDetail) {
  if (detail.status === "needs-fix") {
    return "validation 오류를 해결한 뒤 VM을 시작할 수 있습니다.";
  }
  if (detail.status === "running") {
    return "이미 VM 작업이 실행 중입니다.";
  }
  if (detail.status === "completed") {
    return "완료된 프로젝트는 다시 실행할 수 없습니다.";
  }
  if (detail.status === "failed") {
    return "failed 상태는 reset 후 다시 실행할 수 있습니다.";
  }
  if (detail.vm_job_id) {
    return "이미 VM 작업 ID가 할당된 프로젝트입니다.";
  }
  return null;
}

function ProcessEditor({
  detail,
  annotations,
  processErrors,
}: {
  detail: VmProjectDetail;
  annotations: ProcessAnnotationItem[];
  processErrors: string[];
}) {
  const queryClient = useQueryClient();
  const draft = detail.project_file_draft;
  const [processRows, setProcessRows] = useState<ProjectFileProcess[]>(
    () => cloneProcesses(draft.process),
  );
  const [isToolGuideOpen, setIsToolGuideOpen] = useState(false);

  useEffect(() => {
    setProcessRows(cloneProcesses(draft.process));
  }, [detail.id, draft.process]);

  const processMutation = useMutation({
    mutationFn: (payload: ProcessPatchPayload) =>
      patchVmProjectProcess(detail.id, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["vm-project", detail.id] }),
        queryClient.invalidateQueries({
          queryKey: ["vm-project", detail.id, "process-annotations"],
        }),
        queryClient.invalidateQueries({ queryKey: ["vm-projects"] }),
      ]);
    },
  });

  const isEditable = detail.status === "ready" || detail.status === "needs-fix";
  const errorsByIndex = useMemo(
    () => groupProcessErrorsByIndex(processErrors),
    [processErrors],
  );
  const hasChanges = !areProcessesEqual(processRows, draft.process);
  const canSave =
    isEditable && processRows.length > 0 && hasChanges && !processMutation.isPending;

  if (draft.process.length === 0) {
    return <div className="inline-note">등록된 process가 없습니다.</div>;
  }

  return (
    <form
      className="process-editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (!canSave) return;
        processMutation.mutate({
          process: processRows.map(normalizeProcessForSave),
        });
      }}
    >
      <div className="process-editor__toolbar">
        <div>
          <strong>Tool Data</strong>
          <span>공구 CSV를 9개 입력 칸으로 편집합니다.</span>
        </div>
        <button
          className="button"
          type="button"
          aria-expanded={isToolGuideOpen}
          onClick={() => setIsToolGuideOpen((open) => !open)}
        >
          <HelpCircle aria-hidden="true" size={15} />
          항목 설명
        </button>
      </div>

      {isToolGuideOpen ? <ToolDataGuide /> : null}

      <div className="process-list">
        {processRows.map((process, index) => {
          const annotation = annotations.find((item) => item.index === index);
          const rowErrors = errorsByIndex.get(index) ?? [];
          const toolFields = parseToolData(process.tool_data);
          const toolDataError = getToolDataError(toolFields);
          return (
            <article
              className={`process-item ${
                rowErrors.length || toolDataError ? "process-item--warning" : ""
              }`}
              key={`${index}-${annotation?.workingstep_id ?? process.file_path ?? "process"}`}
            >
              <div className="process-item__header">
                <strong>Process {index + 1}</strong>
                <span>WS: {compactText(annotation?.workingstep_id)}</span>
              </div>

              {rowErrors.length ? (
                <ul className="process-row-errors">
                  {rowErrors.map((error) => (
                    <li key={error}>{error}</li>
                  ))}
                </ul>
              ) : null}

              {toolDataError ? (
                <div className="field-error">{toolDataError}</div>
              ) : null}

              <div className="process-form-grid">
                <label className="form-field">
                  <span>file_path</span>
                  <input
                    value={process.file_path ?? ""}
                    disabled={!isEditable}
                    onChange={(event) =>
                      updateProcessField(
                        setProcessRows,
                        index,
                        "file_path",
                        event.target.value,
                      )
                    }
                  />
                </label>
                <label className="form-field">
                  <span>output_dir_path</span>
                  <input
                    value={process.output_dir_path ?? ""}
                    disabled={!isEditable}
                    onChange={(event) =>
                      updateProcessField(
                        setProcessRows,
                        index,
                        "output_dir_path",
                        event.target.value,
                      )
                    }
                    />
                </label>
              </div>

              <div className="tool-data-editor">
                <div className="tool-data-editor__topline">
                  <span>tool_data</span>
                  <code>{serializeToolData(toolFields)}</code>
                </div>
                <div className="tool-field-grid">
                  {TOOL_FIELD_SPECS.map((spec) => (
                    <label className="form-field" key={spec.key}>
                      <span>{spec.label}</span>
                      <input
                        aria-label={`Process ${index + 1} ${spec.label}`}
                        aria-invalid={Boolean(toolDataError)}
                        disabled={!isEditable}
                        inputMode={spec.inputMode}
                        title={spec.description}
                        value={toolFields[spec.key]}
                        onChange={(event) =>
                          updateProcessToolField(
                            setProcessRows,
                            index,
                            spec.key,
                            event.target.value,
                          )
                        }
                      />
                    </label>
                  ))}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {!isEditable ? (
        <div className="inline-note">
          Process 수정은 ready 또는 needs-fix 상태에서만 가능합니다.
        </div>
      ) : null}
      {processMutation.error instanceof Error ? (
        <div className="empty-state empty-state--error">
          <strong>Process 저장 실패</strong>
          <span>{processMutation.error.message}</span>
        </div>
      ) : null}
      {processMutation.isSuccess ? (
        <div className="inline-note inline-note--success">
          Process 정보를 저장했고 validation 상태를 다시 계산했습니다.
        </div>
      ) : null}

      <div className="form-actions">
        <button
          className="button"
          type="button"
          disabled={!hasChanges || processMutation.isPending}
          onClick={() => {
            setProcessRows(cloneProcesses(draft.process));
            processMutation.reset();
          }}
        >
          되돌리기
        </button>
        <button className="button button--primary" type="submit" disabled={!canSave}>
          {processMutation.isPending ? "저장 중..." : "Process 저장"}
        </button>
      </div>
    </form>
  );
}

const TOOL_FIELD_SPECS = [
  { key: "tNo", label: "T No", description: "tool number", inputMode: "numeric" },
  { key: "dia", label: "Dia", description: "cutter diameter", inputMode: "decimal" },
  { key: "rad", label: "Rad", description: "cutter radius", inputMode: "decimal" },
  {
    key: "eDis",
    label: "eDis",
    description: "radial corner offset",
    inputMode: "decimal",
  },
  {
    key: "fDis",
    label: "fDis",
    description: "axial corner offset",
    inputMode: "decimal",
  },
  { key: "bangl", label: "bangl", description: "tip angle", inputMode: "decimal" },
  { key: "sangl", label: "sangl", description: "flank angle", inputMode: "decimal" },
  { key: "len", label: "Len", description: "cutter height", inputMode: "decimal" },
  { key: "flut", label: "flut", description: "flut number", inputMode: "numeric" },
] as const;

type ToolFieldKey = (typeof TOOL_FIELD_SPECS)[number]["key"];
type ToolDataFields = Record<ToolFieldKey, string>;

const PROCESS_TOOL_GUIDE_IMAGE = "assets/tool_spec.png";

function ToolDataGuide() {
  return (
    <div className="tool-guide">
      <div className="tool-guide-head">
        {TOOL_FIELD_SPECS.map((spec) => (
          <span key={spec.key}>{spec.label}</span>
        ))}
      </div>
      <div className="tool-guide-body">
        {TOOL_FIELD_SPECS.map((spec) => (
          <div className="tool-guide-item" key={spec.key}>
            <strong>{spec.label}</strong>
            <span>{spec.description}</span>
          </div>
        ))}
      </div>
      <figure className="tool-guide-visual">
        <img src={PROCESS_TOOL_GUIDE_IMAGE} alt="Cutting tool guide" />
      </figure>
    </div>
  );
}

function cloneProcesses(processes: ProjectFileProcess[]) {
  return processes.map((process) => ({ ...process }));
}

function normalizeProcessForSave(process: ProjectFileProcess): ProjectFileProcess {
  return {
    file_path: normalizeNullableText(process.file_path),
    output_dir_path: normalizeNullableText(process.output_dir_path),
    tool_data: normalizeNullableText(process.tool_data),
  };
}

function normalizeNullableText(value: string | null) {
  const trimmed = (value ?? "").trim();
  return trimmed ? trimmed : null;
}

function updateProcessField(
  setProcessRows: Dispatch<SetStateAction<ProjectFileProcess[]>>,
  index: number,
  field: keyof ProjectFileProcess,
  value: string,
) {
  setProcessRows((rows) =>
    rows.map((row, rowIndex) =>
      rowIndex === index ? { ...row, [field]: value } : row,
    ),
  );
}

function updateProcessToolField(
  setProcessRows: Dispatch<SetStateAction<ProjectFileProcess[]>>,
  index: number,
  field: ToolFieldKey,
  value: string,
) {
  setProcessRows((rows) =>
    rows.map((row, rowIndex) => {
      if (rowIndex !== index) return row;
      const nextToolFields = {
        ...parseToolData(row.tool_data),
        [field]: value,
      };
      return { ...row, tool_data: serializeToolData(nextToolFields) };
    }),
  );
}

function areProcessesEqual(left: ProjectFileProcess[], right: ProjectFileProcess[]) {
  if (left.length !== right.length) return false;
  return left.every((leftRow, index) => {
    const rightRow = right[index];
    return (
      normalizeNullableText(leftRow.file_path) ===
        normalizeNullableText(rightRow.file_path) &&
      normalizeNullableText(leftRow.output_dir_path) ===
        normalizeNullableText(rightRow.output_dir_path) &&
      normalizeNullableText(leftRow.tool_data) === normalizeNullableText(rightRow.tool_data)
    );
  });
}

function parseToolData(value: string | null | undefined): ToolDataFields {
  const parts = (value ?? "").split(",").map((part) => normalizeToolValue(part));
  return TOOL_FIELD_SPECS.reduce<ToolDataFields>((toolFields, spec, index) => {
    toolFields[spec.key] = parts[index] ?? "";
    return toolFields;
  }, {} as ToolDataFields);
}

function normalizeToolValue(value: string | null | undefined) {
  const trimmed = (value ?? "").trim();
  return trimmed.toLowerCase() === "null" ? "" : trimmed;
}

function serializeToolData(fields: ToolDataFields) {
  return TOOL_FIELD_SPECS.map((spec) => {
    const value = fields[spec.key].trim();
    return value ? value : "null";
  }).join(",");
}

function getToolDataError(fields: ToolDataFields) {
  const missing = TOOL_FIELD_SPECS.filter((spec) => fields[spec.key].trim() === "");
  if (missing.length > 0) {
    return `tool_data에 비어 있는 항목이 있습니다: ${missing
      .map((spec) => spec.label)
      .join(", ")}`;
  }

  const invalid = TOOL_FIELD_SPECS.filter((spec) =>
    Number.isNaN(Number(fields[spec.key].trim())),
  );
  if (invalid.length > 0) {
    return `tool_data는 숫자만 입력할 수 있습니다: ${invalid
      .map((spec) => spec.label)
      .join(", ")}`;
  }

  return null;
}

function groupProcessErrorsByIndex(errors: string[]) {
  const grouped = new Map<number, string[]>();
  for (const error of errors) {
    const match = error.match(/process\[(\d+)\]/i);
    const index = match ? Number(match[1]) - 1 : -1;
    const current = grouped.get(index) ?? [];
    current.push(error);
    grouped.set(index, current);
  }
  return grouped;
}

function MetaItem({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="meta-item">
      <span>{label}</span>
      <strong>{compactText(value)}</strong>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="detail-stack">
      <span className="skeleton skeleton--line" />
      <span className="skeleton skeleton--line short" />
      <span className="skeleton skeleton--block" />
      <span className="skeleton skeleton--block" />
    </div>
  );
}
