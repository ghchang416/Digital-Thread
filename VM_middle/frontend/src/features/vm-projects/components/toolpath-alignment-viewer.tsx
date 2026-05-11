import { lazy, Suspense, useMemo, useState } from "react";

import { useQuery } from "@tanstack/react-query";

import { getToolpathPreview } from "@/features/vm-projects/api/vm-projects-api";
import type {
  StockBox,
  ViewMode,
} from "@/features/vm-projects/components/toolpath-alignment-canvas";

const ToolpathAlignmentCanvas = lazy(() =>
  import("@/features/vm-projects/components/toolpath-alignment-canvas").then(
    (module) => ({ default: module.ToolpathAlignmentCanvas }),
  ),
);

export interface StockSizeDraft {
  xMin: string;
  xMax: string;
  yMin: string;
  yMax: string;
  zMin: string;
  zMax: string;
}

interface ToolpathAlignmentPanelProps {
  projectId: string;
  processCount: number;
  stockSizeFields: StockSizeDraft;
  stockSizeError: string | null;
}

const SEGMENT_COLORS: Record<string, number> = {
  FEED: 0x4f8f12,
  RAPID: 0xb42318,
  PLUNGE: 0x0047bb,
  RETRACT: 0xa15c07,
  SKIM: 0x736273,
  LEAD_LINK: 0x8a5a00,
};

export function ToolpathAlignmentPanel({
  projectId,
  processCount,
  stockSizeFields,
  stockSizeError,
}: ToolpathAlignmentPanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("iso");
  const toolpathQuery = useQuery({
    queryKey: ["toolpath-preview", projectId],
    queryFn: () => getToolpathPreview(projectId),
    staleTime: 1000 * 60,
  });

  const draftStock = useMemo(
    () => parseDraftStockBox(stockSizeFields, stockSizeError),
    [stockSizeFields, stockSizeError],
  );
  const apiStock = toolpathQuery.data?.stock
    ? { min: toolpathQuery.data.stock.min, max: toolpathQuery.data.stock.max }
    : null;
  const stockBox = draftStock ?? apiStock;
  const metrics = stockBox ? getStockBoxMetrics(stockBox) : null;
  const summary = toolpathQuery.data?.summary;
  const hasNoToolpath =
    toolpathQuery.isSuccess && (summary?.segment_count ?? 0) === 0;

  return (
    <aside className="stock-preview" aria-label="Toolpath and stock alignment preview">
      <div className="stock-preview__header">
        <div>
          <span>NC overlay</span>
          <strong>Toolpath Alignment</strong>
        </div>
        <div className="stock-preview__badges">
          {summary?.truncated ? <span className="preview-badge">sampled</span> : null}
          <span className="preview-badge preview-badge--live">3D</span>
        </div>
      </div>

      <div className="viewer-toolbar" aria-label="3D view controls">
        {(["iso", "top", "front", "side", "fit"] as const).map((mode) => (
          <button
            className={`viewer-toolbar__button ${viewMode === mode ? "viewer-toolbar__button--active" : ""}`}
            key={mode}
            type="button"
            onClick={() => setViewMode(mode)}
          >
            {mode.toUpperCase()}
          </button>
        ))}
      </div>

      <Suspense
        fallback={
          <div className="stock-preview__canvas stock-preview__canvas--webgl viewer-canvas-fallback">
            3D viewer를 준비하는 중입니다.
          </div>
        }
      >
        <ToolpathAlignmentCanvas
          stockBox={stockBox}
          segments={toolpathQuery.data?.segments ?? []}
          bounds={toolpathQuery.data}
          viewMode={viewMode}
        />
      </Suspense>

      {toolpathQuery.isLoading ? (
        <div className="viewer-state">NC toolpath를 불러오는 중입니다.</div>
      ) : null}
      {toolpathQuery.error instanceof Error ? (
        <div className="viewer-state viewer-state--error">
          {toolpathQuery.error.message}
        </div>
      ) : null}
      {stockSizeError ? (
        <div className="viewer-state viewer-state--warning">
          Stock 좌표가 유효하지 않아 소재 box는 마지막 유효 상태로 표시됩니다.
        </div>
      ) : null}
      {hasNoToolpath ? (
        <div className="viewer-state">
          표시할 NC segment가 없습니다. ncdata.zip 또는 process file_path를 확인하세요.
        </div>
      ) : null}

      {summary ? (
        <div className="viewer-summary">
          <span>
            {summary.returned_segment_count.toLocaleString()} /{" "}
            {summary.segment_count.toLocaleString()} segments
          </span>
          <span>{summary.sampling === "uniform" ? "uniform sampling" : "full preview"}</span>
        </div>
      ) : null}

      <div className="stock-preview__metrics">
        <Metric label="x_span" value={metrics?.xSpan ?? "-"} />
        <Metric label="y_span" value={metrics?.ySpan ?? "-"} />
        <Metric label="z_span" value={metrics?.zSpan ?? "-"} />
        <Metric label="nc_steps" value={String(processCount)} />
      </div>

      <div className="toolpath-legend" aria-label="Toolpath segment type legend">
        {Object.entries(SEGMENT_COLORS).slice(0, 5).map(([type, color]) => (
          <span key={type}>
            <i style={{ backgroundColor: `#${color.toString(16).padStart(6, "0")}` }} />
            {type}
          </span>
        ))}
      </div>

      {summary?.errors.length ? (
        <details className="viewer-errors">
          <summary>Preview notes ({summary.errors.length})</summary>
          <ul>
            {summary.errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </aside>
  );
}

function parseDraftStockBox(fields: StockSizeDraft, error: string | null): StockBox | null {
  if (error) return null;
  const xMin = Number(fields.xMin);
  const xMax = Number(fields.xMax);
  const yMin = Number(fields.yMin);
  const yMax = Number(fields.yMax);
  const zMin = Number(fields.zMin);
  const zMax = Number(fields.zMax);
  if ([xMin, xMax, yMin, yMax, zMin, zMax].some(Number.isNaN)) return null;
  return {
    min: [xMin, yMin, zMin],
    max: [xMax, yMax, zMax],
  };
}

function getStockBoxMetrics(stockBox: StockBox) {
  return {
    xSpan: `${formatMetricValue(stockBox.max[0] - stockBox.min[0])} mm`,
    ySpan: `${formatMetricValue(stockBox.max[1] - stockBox.min[1])} mm`,
    zSpan: `${formatMetricValue(stockBox.max[2] - stockBox.min[2])} mm`,
  };
}

function formatMetricValue(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="meta-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
