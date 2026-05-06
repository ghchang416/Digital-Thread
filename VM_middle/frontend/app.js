const API = {
  vmProjects: "/api/v1/vm-project",
  stocks: "/api/v1/vm-project/stocks",
  dpProjects: "/api/v1/dp/projects",
  dpWorkplans: "/api/v1/dp/projects/workplans",
  dpThumbnail: "/api/v1/dp/projects/thumbnail",
  isoProjects: "/api/v1/iso-projects",
};

const STOCK_BOUND_KEYS = [
  "min_x",
  "max_x",
  "min_y",
  "max_y",
  "min_z",
  "max_z",
];

const TOOL_FIELD_SPECS = [
  { key: "tNo", label: "T No", desc: "tool number" },
  { key: "dia", label: "Dia", desc: "cutter diameter" },
  { key: "rad", label: "Rad", desc: "cutter radius" },
  { key: "eDis", label: "eDis", desc: "radial corner offset" },
  { key: "fDis", label: "fDis", desc: "axial corner offset" },
  { key: "bangl", label: "bangl", desc: "tip angle" },
  { key: "sangl", label: "sangl", desc: "flank angle" },
  { key: "len", label: "Len", desc: "cutter height" },
  { key: "flut", label: "flut", desc: "flut number" },
];

const PROCESS_TOOL_GUIDE_IMAGE = "/ui/src/tool_spec.png";

const state = {
  notice: null,
  stocks: [],
  vm: {
    items: [],
    total: 0,
    page: 1,
    size: 12,
    hasMore: false,
    q: "",
    status: "",
    loading: false,
    detailLoading: false,
    selectedId: null,
    detail: null,
    processAnnotations: [],
    actionLoading: false,
  },
  editor: {
    stockType: "",
    stockBounds: {
      min_x: "",
      max_x: "",
      min_y: "",
      max_y: "",
      min_z: "",
      max_z: "",
    },
    process: [],
  },
  sourceMode: "dp",
  sources: {
    dp: {
      items: [],
      page: 0,
      size: 10,
      total: 0,
      q: "",
      loading: false,
      loaded: false,
    },
    iso: {
      items: [],
      offset: 0,
      limit: 20,
      total: 0,
      hasMore: false,
      loading: false,
      loaded: false,
    },
  },
  selectedSourceProject: null,
  sourceThumbnailKey: "",
  workplans: [],
  selectedWorkplan: "",
  workplansLoading: false,
  createLoading: false,
  startUploadMode: "file",
  ui: {
    detailOpen: false,
    processHelpOpen: true,
  },
};

const app = document.getElementById("app");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function statusLabel(status) {
  switch (status) {
    case "needs-fix":
      return "Needs Fix";
    case "ready":
      return "Ready";
    case "running":
      return "Running";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default:
      return status || "-";
  }
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function emptyStockBounds() {
  return {
    min_x: "",
    max_x: "",
    min_y: "",
    max_y: "",
    min_z: "",
    max_z: "",
  };
}

function parseStockSize(value) {
  const bounds = emptyStockBounds();
  if (!value) return bounds;
  const parts = String(value).split(",").map((part) => part.trim());
  STOCK_BOUND_KEYS.forEach((key, index) => {
    bounds[key] = parts[index] || "";
  });
  return bounds;
}

function serializeStockSize(bounds) {
  return STOCK_BOUND_KEYS.map((key) => String(bounds[key] || "").trim()).join(",");
}

function normalizeToolValue(value) {
  const raw = String(value ?? "").trim();
  if (!raw || raw.toLowerCase() === "null") {
    return "";
  }
  return raw;
}

function parseToolData(value) {
  const parts = String(value || "")
    .split(",")
    .map((part) => part.trim());

  const parsed = {};
  TOOL_FIELD_SPECS.forEach((spec, index) => {
    parsed[spec.key] = normalizeToolValue(parts[index]);
  });
  return parsed;
}

function serializeToolData(tool) {
  return TOOL_FIELD_SPECS.map((spec) => {
    const raw = String(tool?.[spec.key] ?? "").trim();
    return raw ? raw : "null";
  }).join(",");
}

function vmThumbnailUrl(id) {
  return `${API.vmProjects}/${encodeURIComponent(id)}/thumbnail`;
}

function vmProcessAnnotationsUrl(id) {
  return `${API.vmProjects}/${encodeURIComponent(id)}/process-annotations`;
}

function dpThumbnailUrl(project) {
  const params = new URLSearchParams({
    gid: project.gid,
    aid: project.aid,
    eid: project.eid,
  });
  return `${API.dpThumbnail}?${params.toString()}`;
}

function isEditable(detail) {
  if (!detail) return false;
  return detail.status === "ready" || detail.status === "needs-fix";
}

function canCreate() {
  if (!state.selectedSourceProject || state.createLoading) {
    return false;
  }
  if (state.workplansLoading) {
    return false;
  }
  if (state.workplans.length === 0) {
    return true;
  }
  return Boolean(state.selectedWorkplan);
}

async function apiJson(url, options = {}) {
  const headers = new Headers(options.headers || {});
  let body = options.body;

  if (body && typeof body === "object" && !(body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const response = await fetch(url, {
    ...options,
    headers,
    body,
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    let detail =
      payload?.detail ?? payload?.message ?? response.statusText ?? "요청 실패";
    if (typeof detail === "object") {
      detail = detail.message || JSON.stringify(detail);
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return payload;
}

function setNotice(type, text) {
  state.notice = { type, text };
  render();
}

function clearNotice() {
  state.notice = null;
  render();
}

function syncEditorFromDetail(detail) {
  const draft = detail?.project_file_draft || {};
  state.editor = {
    stockType: draft.stock_type || "",
    stockBounds: parseStockSize(draft.stock_size || ""),
    process: Array.isArray(draft.process)
      ? draft.process.map((item) => ({
          file_path: item.file_path || "",
          output_dir_path: item.output_dir_path || "",
          tool_data: item.tool_data || "",
          tool: parseToolData(item.tool_data || ""),
        }))
      : [],
  };
}

async function loadStocks() {
  state.stocks = (await apiJson(API.stocks)).items || [];
}

async function loadVmProjects({ keepSelection = true } = {}) {
  state.vm.loading = true;
  render();

  try {
    const params = new URLSearchParams({
      page: String(state.vm.page),
      size: String(state.vm.size),
    });
    if (state.vm.q.trim()) params.set("q", state.vm.q.trim());
    if (state.vm.status) params.set("status", state.vm.status);

    const data = await apiJson(`${API.vmProjects}?${params.toString()}`);
    state.vm.items = data.items || [];
    state.vm.total = data.total || 0;
    state.vm.hasMore = Boolean(data.has_more);

    const hasSelection =
      keepSelection &&
      state.vm.selectedId &&
      state.vm.items.some((item) => item.id === state.vm.selectedId);

    if (!hasSelection) {
      state.vm.selectedId = state.vm.items[0]?.id || null;
    }
  } finally {
    state.vm.loading = false;
    render();
  }

  if (state.vm.selectedId) {
    await loadVmDetail(state.vm.selectedId);
  } else {
    state.vm.detail = null;
    state.vm.processAnnotations = [];
    syncEditorFromDetail(null);
    render();
  }
}

async function loadVmDetail(id) {
  if (!id) return;
  state.vm.selectedId = id;
  state.vm.detailLoading = true;
  render();

  const currentId = id;
  try {
    const [detail, annotations] = await Promise.all([
      apiJson(`${API.vmProjects}/${encodeURIComponent(id)}`),
      apiJson(vmProcessAnnotationsUrl(id)).catch(() => ({ items: [] })),
    ]);
    if (state.vm.selectedId !== currentId) return;
    state.vm.detail = detail;
    state.vm.processAnnotations = annotations.items || [];
    syncEditorFromDetail(detail);
  } catch (error) {
    if (state.vm.selectedId === currentId) {
      state.vm.detail = null;
      state.vm.processAnnotations = [];
      syncEditorFromDetail(null);
    }
    throw error;
  } finally {
    if (state.vm.selectedId === currentId) {
      state.vm.detailLoading = false;
      render();
    }
  }
}

async function loadSourceProjects(mode, { append = false } = {}) {
  const source = state.sources[mode];
  source.loading = true;
  render();

  try {
    if (mode === "dp") {
      const params = new URLSearchParams({
        page: String(source.page),
        size: String(source.size),
      });
      if (source.q.trim()) {
        params.set("q", source.q.trim());
      }
      const data = await apiJson(`${API.dpProjects}?${params.toString()}`);
      source.items = append ? [...source.items, ...(data.items || [])] : data.items || [];
      source.total = data.total || 0;
      source.loaded = true;
    } else {
      const params = new URLSearchParams({
        offset: String(source.offset),
        limit: String(source.limit),
      });
      const data = await apiJson(`${API.isoProjects}?${params.toString()}`);
      source.items = append ? [...source.items, ...(data.items || [])] : data.items || [];
      source.total = data.total || 0;
      source.hasMore = Boolean(data.has_more);
      source.loaded = true;
    }
  } finally {
    source.loading = false;
    render();
  }
}

async function ensureSourceLoaded(mode) {
  const source = state.sources[mode];
  if (!source.loaded && !source.loading) {
    await loadSourceProjects(mode);
  }
}

function getSourcePager(mode) {
  const source = state.sources[mode];
  if (mode === "dp") {
    const totalPages = Math.max(1, Math.ceil((source.total || 0) / source.size));
    return {
      label: `${source.page + 1} / ${totalPages}`,
      canPrev: source.page > 0,
      canNext: source.page + 1 < totalPages,
    };
  }

  const currentPage = Math.floor(source.offset / source.limit) + 1;
  const totalPages = Math.max(1, Math.ceil((source.total || 0) / source.limit));
  return {
    label: `${currentPage} / ${totalPages}`,
    canPrev: source.offset > 0,
    canNext: Boolean(source.hasMore),
  };
}

function buildIsoWorkplans(project) {
  const values = Array.isArray(project?.wpid) ? project.wpid : [];
  if (values.length > 0) {
    return values.map((wpid) => ({
      wpid,
      ws_count: null,
      pattern: "ISO",
    }));
  }
  if (project?.main_wpid) {
    return [{ wpid: project.main_wpid, ws_count: null, pattern: "ISO" }];
  }
  return [];
}

async function selectSourceProject(project) {
  state.selectedSourceProject = project;
  state.workplans = [];
  state.selectedWorkplan = "";
  state.sourceThumbnailKey =
    project && state.sourceMode === "dp"
      ? `${project.gid}|${project.aid}|${project.eid}`
      : "";
  render();

  if (!project) return;

  if (state.sourceMode === "dp") {
    state.workplansLoading = true;
    render();
    try {
      const params = new URLSearchParams({
        gid: project.gid,
        aid: project.aid,
        eid: project.eid,
      });
      const data = await apiJson(`${API.dpWorkplans}?${params.toString()}`);
      state.workplans = data.workplans || [];
    } finally {
      state.workplansLoading = false;
      state.selectedWorkplan = state.workplans[0]?.wpid || "";
      render();
    }
  } else {
    state.workplans = buildIsoWorkplans(project);
    state.selectedWorkplan = state.workplans[0]?.wpid || "";
    render();
  }
}

async function createVmProject() {
  if (!canCreate()) return;

  state.createLoading = true;
  render();
  try {
    const payload = {
      source: state.sourceMode,
      gid: state.selectedSourceProject.gid,
      aid: state.selectedSourceProject.aid,
      eid: state.selectedSourceProject.eid,
    };
    if (state.selectedWorkplan) {
      payload.wpid = state.selectedWorkplan;
    }

    const result = await apiJson(API.vmProjects, {
      method: "POST",
      body: payload,
    });

    setNotice(
      "success",
      `VM 프로젝트를 생성했습니다. 상태: ${statusLabel(result.status)}`
    );

    state.vm.page = 1;
    await loadVmProjects({ keepSelection: false });

    const createdId = result.vm_project_id || result.id;
    if (createdId) {
      state.ui.detailOpen = true;
      await loadVmDetail(createdId);
    }
  } catch (error) {
    setNotice("error", error.message);
  } finally {
    state.createLoading = false;
    render();
  }
}

async function saveStock() {
  if (!state.vm.detail) return;
  state.vm.actionLoading = true;
  render();
  try {
    await apiJson(
      `${API.vmProjects}/${encodeURIComponent(state.vm.detail.id)}/project-file/stock`,
      {
        method: "PATCH",
        body: {
          stock_type: state.editor.stockType || null,
          stock_size: serializeStockSize(state.editor.stockBounds) || null,
        },
      }
    );
    await loadVmDetail(state.vm.detail.id);
    setNotice("success", "Stock 정보를 저장했습니다.");
  } catch (error) {
    setNotice("error", error.message);
  } finally {
    state.vm.actionLoading = false;
    render();
  }
}

async function saveProcess() {
  if (!state.vm.detail) return;
  state.vm.actionLoading = true;
  render();
  try {
    await apiJson(
      `${API.vmProjects}/${encodeURIComponent(state.vm.detail.id)}/project-file/process`,
      {
        method: "PATCH",
        body: {
          process: state.editor.process.map((item) => ({
            file_path: item.file_path || null,
            output_dir_path: item.output_dir_path || null,
            tool_data: serializeToolData(item.tool) || null,
          })),
        },
      }
    );
    await loadVmDetail(state.vm.detail.id);
    setNotice("success", "Process 정보를 저장했습니다.");
  } catch (error) {
    setNotice("error", error.message);
  } finally {
    state.vm.actionLoading = false;
    render();
  }
}

async function startVm() {
  if (!state.vm.detail) return;
  state.vm.actionLoading = true;
  render();
  try {
    const result = await apiJson(
      `${API.vmProjects}/${encodeURIComponent(state.vm.detail.id)}/start-vm`,
      {
        method: "POST",
        body: { upload_mode: state.startUploadMode },
      }
    );
    setNotice(
      "success",
      `VM 작업을 시작했습니다. job_id=${result.vm_job_id || "-"}`
    );
    await loadVmDetail(state.vm.detail.id);
    await loadVmProjects();
  } catch (error) {
    setNotice("error", error.message);
  } finally {
    state.vm.actionLoading = false;
    render();
  }
}

async function pollVm() {
  if (!state.vm.detail) return;
  state.vm.actionLoading = true;
  render();
  try {
    await apiJson(`${API.vmProjects}/${encodeURIComponent(state.vm.detail.id)}/poll`, {
      method: "POST",
    });
    await loadVmDetail(state.vm.detail.id);
    await loadVmProjects();
    setNotice("success", "VM 상태를 새로 확인했습니다.");
  } catch (error) {
    setNotice("error", error.message);
  } finally {
    state.vm.actionLoading = false;
    render();
  }
}

async function resetVm() {
  if (!state.vm.detail) return;
  state.vm.actionLoading = true;
  render();
  try {
    await apiJson(`${API.vmProjects}/${encodeURIComponent(state.vm.detail.id)}/reset`, {
      method: "POST",
    });
    await loadVmDetail(state.vm.detail.id);
    await loadVmProjects();
    setNotice("success", "failed 상태를 ready로 리셋했습니다.");
  } catch (error) {
    setNotice("error", error.message);
  } finally {
    state.vm.actionLoading = false;
    render();
  }
}

function closeDetailDrawer() {
  state.ui.detailOpen = false;
  render();
}

function toggleProcessHelp() {
  state.ui.processHelpOpen = !state.ui.processHelpOpen;
  render();
}

function renderVmList() {
  if (state.vm.loading) {
    return '<div class="loading">VM 프로젝트 목록을 불러오는 중입니다.</div>';
  }
  if (state.vm.items.length === 0) {
    return '<div class="empty">표시할 VM 프로젝트가 없습니다.</div>';
  }

  return `<div class="project-list">${state.vm.items
    .map((item) => {
      const selected = item.id === state.vm.selectedId ? "is-selected" : "";
      const thumb = item.source === "dp";
      return `
        <div class="project-row ${selected}">
          <button type="button" data-action="select-vm" data-id="${escapeHtml(item.id)}">
            <div class="project-card">
              <div class="project-thumb ${thumb ? "has-image" : ""}">
                ${
                  thumb
                    ? `<img data-thumb-image src="${escapeHtml(vmThumbnailUrl(item.id))}" alt="" />`
                    : ""
                }
                <div class="thumb-placeholder">No image</div>
              </div>
              <div>
                <div class="row between">
                  <span class="project-name">${escapeHtml(
                    item.display_name || item.proj_name || item.eid
                  )}</span>
                  <span class="chip ${escapeHtml(item.status)}">${escapeHtml(
                    statusLabel(item.status)
                  )}</span>
                </div>
                <div class="project-meta">
                  <span><span class="code">${escapeHtml(item.source)}</span> / ${escapeHtml(
                    item.eid
                  )}</span>
                  <span>workplan ${escapeHtml(item.wpid || "-")}</span>
                  <span>validation ${escapeHtml(item.validation_error_count)}</span>
                </div>
              </div>
            </div>
          </button>
        </div>
      `;
    })
    .join("")}</div>`;
}

function renderSourceList(mode) {
  const source = state.sources[mode];
  if (source.loading && source.items.length === 0) {
    return '<div class="loading">프로젝트 목록을 불러오는 중입니다.</div>';
  }
  if (source.items.length === 0) {
    return '<div class="empty">표시할 소스 프로젝트가 없습니다.</div>';
  }

  return `<div class="source-list">${source.items
    .map((item) => {
      const selected =
        state.selectedSourceProject &&
        item.gid === state.selectedSourceProject.gid &&
        item.aid === state.selectedSourceProject.aid &&
        item.eid === state.selectedSourceProject.eid
          ? "is-selected"
          : "";
      return `
        <div class="source-row ${selected}">
          <button
            type="button"
            data-action="select-source"
            data-mode="${escapeHtml(mode)}"
            data-gid="${escapeHtml(item.gid)}"
            data-aid="${escapeHtml(item.aid)}"
            data-eid="${escapeHtml(item.eid)}"
          >
            <div class="source-card">
              <strong>${escapeHtml(item.display_name || item.name || item.eid)}</strong>
              <div class="source-meta">
                <span>gid: ${escapeHtml(item.gid)}</span>
                <span>aid: ${escapeHtml(item.aid)}</span>
                <span>eid: ${escapeHtml(item.eid)}</span>
                ${
                  mode === "iso"
                    ? `<span>workplans: ${escapeHtml(
                        Array.isArray(item.wpid) ? item.wpid.length : 0
                      )}</span>`
                    : `<span>type: ${escapeHtml(item.asset_type || "-")}</span>`
                }
              </div>
            </div>
          </button>
        </div>
      `;
    })
    .join("")}</div>`;
}

function renderSourcePager(mode) {
  const pager = getSourcePager(mode);
  return `
    <div class="source-pager">
      <button class="btn ghost" type="button" data-action="source-prev" ${
        pager.canPrev ? "" : "disabled"
      }>이전</button>
      <span class="subtle">${escapeHtml(pager.label)}</span>
      <button class="btn ghost" type="button" data-action="source-next" ${
        pager.canNext ? "" : "disabled"
      }>다음</button>
    </div>
  `;
}

function renderSourceFilters(mode) {
  if (mode !== "dp") {
    return "";
  }

  return `
    <form id="source-filter-form" class="source-filter-bar">
      <input
        id="source-search-input"
        class="input"
        name="q"
        value="${escapeHtml(state.sources.dp.q)}"
        placeholder="DP 프로젝트 검색"
      />
      <button class="btn primary" type="submit">검색</button>
      <button class="btn ghost" type="button" data-action="clear-source-filter">초기화</button>
    </form>
  `;
}

function renderWorkplans() {
  if (!state.selectedSourceProject) {
    return '<div class="empty">프로젝트를 선택하면 workplan 목록이 표시됩니다.</div>';
  }
  if (state.workplansLoading) {
    return '<div class="loading">workplan을 조회하는 중입니다.</div>';
  }
  if (state.workplans.length === 0) {
    return '<div class="empty">선택 가능한 workplan이 없습니다. wpid 없이 생성할 수 있습니다.</div>';
  }

  return `<div class="workplan-list">${state.workplans
    .map((item, index) => {
      const checked = item.wpid === state.selectedWorkplan ? "checked" : "";
      return `
        <label class="workplan-option">
          <input
            type="radio"
            name="workplan"
            value="${escapeHtml(item.wpid || "")}"
            data-action="select-workplan"
            ${checked}
          />
          <span class="workplan-copy">
            <strong>${escapeHtml(item.wpid || `workplan-${index + 1}`)}</strong>
            <span>pattern: ${escapeHtml(item.pattern || state.sourceMode.toUpperCase())}</span>
            <span>workingstep count: ${escapeHtml(item.ws_count ?? "-")}</span>
          </span>
        </label>
      `;
    })
    .join("")}</div>`;
}

function renderSourcePreview() {
  if (!state.selectedSourceProject) {
    return '<div class="empty">왼쪽에서 ISO 또는 DP 프로젝트를 선택해 주세요.</div>';
  }

  const isDp = state.sourceMode === "dp";
  return `
    <div class="source-preview">
      <div class="source-hero">
        <div class="thumb-frame ${isDp ? "has-image" : ""}">
          ${
            isDp
              ? `<img data-thumb-image src="${escapeHtml(
                  dpThumbnailUrl(state.selectedSourceProject)
                )}" alt="" />`
              : ""
          }
          <div class="thumb-placeholder">No image</div>
        </div>
        <div class="source-hero-copy">
          <div class="row between">
            <strong class="project-name">${escapeHtml(
              state.selectedSourceProject.display_name ||
                state.selectedSourceProject.name ||
                state.selectedSourceProject.eid
            )}</strong>
            <span class="code">${escapeHtml(state.sourceMode.toUpperCase())}</span>
          </div>
          <div class="source-meta">
            <span>gid: ${escapeHtml(state.selectedSourceProject.gid)}</span>
            <span>aid: ${escapeHtml(state.selectedSourceProject.aid)}</span>
            <span>eid: ${escapeHtml(state.selectedSourceProject.eid)}</span>
            <span>selected workplan: ${escapeHtml(state.selectedWorkplan || "-")}</span>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderDetailPanel() {
  if (state.vm.detailLoading) {
    return '<div class="loading">프로젝트 상세를 불러오는 중입니다.</div>';
  }
  if (!state.vm.detail) {
    return '<div class="empty">프로젝트를 선택하면 상세와 편집 화면이 표시됩니다.</div>';
  }

  const detail = state.vm.detail;
  const editable = isEditable(detail);
  const process = state.editor.process || [];
  const processAnnotations = state.vm.processAnnotations || [];

  return `
    <div class="stack">
      <div class="row between">
        <div>
          <h2 class="title">${escapeHtml(
            detail.display_name || detail.proj_name || detail.eid
          )}</h2>
          <div class="subtle">선택한 프로젝트의 공정 정보와 실행 상태를 확인합니다.</div>
        </div>
        <span class="chip ${escapeHtml(detail.status)}">${escapeHtml(
          statusLabel(detail.status)
        )}</span>
      </div>

      <div class="stat-grid">
        <div class="stat">
          <strong>Source</strong>
          <span>${escapeHtml(detail.source)}</span>
        </div>
        <div class="stat">
          <strong>Validation</strong>
          <span>${detail.validation_is_valid ? "valid" : "needs review"}</span>
        </div>
        <div class="stat">
          <strong>Process Count</strong>
          <span>${escapeHtml(process.length)}</span>
        </div>
      </div>

      <div class="meta-grid">
        <div class="meta-item"><strong>gid</strong><span>${escapeHtml(detail.gid)}</span></div>
        <div class="meta-item"><strong>aid</strong><span>${escapeHtml(detail.aid)}</span></div>
        <div class="meta-item"><strong>eid</strong><span>${escapeHtml(detail.eid)}</span></div>
        <div class="meta-item"><strong>wpid</strong><span>${escapeHtml(detail.wpid || "-")}</span></div>
        <div class="meta-item"><strong>Created</strong><span>${escapeHtml(
          formatDate(detail.created_at)
        )}</span></div>
        <div class="meta-item"><strong>Updated</strong><span>${escapeHtml(
          formatDate(detail.updated_at)
        )}</span></div>
      </div>

      <div class="divider"></div>

      <section class="stack">
        <div class="row between">
          <div>
            <h3 class="section-title">Stock</h3>
            <div class="subtle">소재 종류와 가공 기준 좌표 범위를 입력합니다. ready / needs-fix 상태에서만 수정할 수 있습니다.</div>
          </div>
          <button class="btn primary" data-action="save-stock" ${
            editable && !state.vm.actionLoading ? "" : "disabled"
          }>Stock 저장</button>
        </div>
        <div class="field-grid">
          <div class="field">
            <label for="stock-type-select">Stock Type</label>
            <select id="stock-type-select" class="select" ${
              editable ? "" : "disabled"
            }>
              <option value="">선택</option>
              ${state.stocks
                .map(
                  (item) => `
                    <option value="${escapeHtml(item.code)}" ${
                      item.code === state.editor.stockType ? "selected" : ""
                    }>
                      ${escapeHtml(item.code)} - ${escapeHtml(item.name)}
                    </option>
                  `
                )
                .join("")}
            </select>
          </div>
          <div class="field">
            <label>Stock Bounds</label>
            <div class="stock-grid">
              ${STOCK_BOUND_KEYS.map(
                (key) => `
                  <div class="field">
                    <label for="stock-bound-${key}">${escapeHtml(key)}</label>
                    <input
                      id="stock-bound-${key}"
                      class="input"
                      data-stock-bound="${escapeHtml(key)}"
                      value="${escapeHtml(state.editor.stockBounds[key] || "")}"
                      ${editable ? "" : "disabled"}
                    />
                  </div>
                `
              ).join("")}
            </div>
          </div>
        </div>
      </section>

      <div class="divider"></div>

      <section class="stack">
        <div class="row between">
          <div>
            <h3 class="section-title">Process</h3>
            <div class="subtle">NC와 워킹스텝 기준으로 생성된 공정입니다. 공구 정보만 수정할 수 있습니다.</div>
          </div>
          <div class="row">
            <button class="btn ghost" data-action="toggle-process-help">항목 설명</button>
            <button class="btn primary" data-action="save-process" ${
              editable && !state.vm.actionLoading ? "" : "disabled"
            }>Process 저장</button>
          </div>
        </div>
        ${
          state.ui.processHelpOpen
            ? `
              <div class="tool-guide">
                <div class="tool-guide-head">
                  ${TOOL_FIELD_SPECS.map(
                    (spec) => `<span>${escapeHtml(spec.label)}</span>`
                  ).join("")}
                </div>
                <div class="tool-guide-body compact">
                  ${TOOL_FIELD_SPECS.map(
                    (spec) => `
                      <div class="tool-guide-item compact">
                        <strong>${escapeHtml(spec.label)}</strong>
                        <span>${escapeHtml(spec.desc)}</span>
                      </div>
                    `
                  ).join("")}
                </div>
                <figure class="tool-guide-visual large">
                  <img src="${PROCESS_TOOL_GUIDE_IMAGE}" alt="Cutting tool guide" />
                </figure>
              </div>
            `
            : ""
        }
        <div class="process-list">
          ${
            process.length === 0
              ? '<div class="empty">등록된 process가 없습니다.</div>'
              : process
                  .map(
                    (item, index) => `
                      <div class="process-row">
                        <div class="process-head">
                          <div class="process-title-block">
                            <span class="process-index">Process ${index + 1}</span>
                            <span class="process-ws">WS: ${escapeHtml(
                              processAnnotations.find((meta) => meta.index === index)
                                ?.workingstep_id || "-"
                            )}</span>
                          </div>
                        </div>
                        <div class="tool-field-grid">
                          ${TOOL_FIELD_SPECS.map(
                            (spec) => `
                              <div class="field">
                                <label>${escapeHtml(spec.label)}</label>
                                <input
                                  class="input"
                                  data-tool-field="${escapeHtml(spec.key)}"
                                  data-index="${index}"
                                  value="${escapeHtml(item.tool?.[spec.key] || "")}"
                                  ${editable ? "" : "disabled"}
                                />
                              </div>
                            `
                          ).join("")}
                        </div>
                      </div>
                    `
                  )
                  .join("")
          }
        </div>
      </section>

      <div class="divider"></div>

      <section class="stack">
        <div class="row between">
          <div>
            <h3 class="section-title">Validation</h3>
            <div class="subtle">백엔드 validation 결과와 VM 실행 상태입니다.</div>
          </div>
          <div class="row">
            <button class="btn ghost" data-action="reload-detail">새로고침</button>
            <button class="btn warn" data-action="poll-vm" ${
              detail.status === "running" && !state.vm.actionLoading ? "" : "disabled"
            }>Poll</button>
            <button class="btn warn" data-action="reset-vm" ${
              detail.status === "failed" && !state.vm.actionLoading ? "" : "disabled"
            }>Reset</button>
          </div>
        </div>
        ${
          Array.isArray(detail.validation_errors) && detail.validation_errors.length > 0
            ? `<ul class="validation-list">${detail.validation_errors
                .map((item) => `<li>${escapeHtml(item)}</li>`)
                .join("")}</ul>`
            : '<div class="empty">validation error가 없습니다.</div>'
        }
        <div class="meta-grid">
          <div class="meta-item"><strong>upload_mode</strong><span>${escapeHtml(
            detail.upload_mode || "-"
          )}</span></div>
          <div class="meta-item"><strong>vm_job_id</strong><span>${escapeHtml(
            detail.vm_job_id || "-"
          )}</span></div>
          <div class="meta-item"><strong>vm_raw_status</strong><span>${escapeHtml(
            detail.vm_raw_status || "-"
          )}</span></div>
          <div class="meta-item"><strong>vm_last_polled_at</strong><span>${escapeHtml(
            formatDate(detail.vm_last_polled_at)
          )}</span></div>
          <div class="meta-item"><strong>vm_error_message</strong><span>${escapeHtml(
            detail.vm_error_message || "-"
          )}</span></div>
          <div class="meta-item"><strong>result_seq_id</strong><span>${escapeHtml(
            detail.vm_result_upload?.seq_id ?? "-"
          )}</span></div>
          <div class="meta-item"><strong>uploaded</strong><span>${escapeHtml(
            detail.vm_result_upload
              ? `${detail.vm_result_upload.uploaded_indices?.length || 0} / ${detail.vm_result_upload.total_count || 0}`
              : "-"
          )}</span></div>
          <div class="meta-item"><strong>last_uploaded</strong><span>${escapeHtml(
            detail.vm_result_upload?.last_uploaded_element_id || "-"
          )}</span></div>
          <div class="meta-item"><strong>failed_process</strong><span>${escapeHtml(
            detail.vm_result_upload?.failed_index ?? "-"
          )}</span></div>
          <div class="meta-item"><strong>upload_error</strong><span>${escapeHtml(
            detail.vm_result_upload?.error_message || "-"
          )}</span></div>
        </div>
      </section>

      <div class="divider"></div>

      <section class="stack">
        <div>
          <h3 class="section-title">VM Start</h3>
          <div class="subtle">status가 ready일 때만 실행할 수 있습니다.</div>
        </div>
        <div class="row">
          <label class="workplan-option">
            <input
              type="radio"
              name="upload-mode"
              value="file"
              data-action="upload-mode"
              ${state.startUploadMode === "file" ? "checked" : ""}
            />
            <span class="workplan-copy">
              <strong>파일 업로드</strong>
              <span>결과 ZIP을 다운로드 후 실제 파일로 등록합니다.</span>
            </span>
          </label>
          <label class="workplan-option">
            <input
              type="radio"
              name="upload-mode"
              value="link"
              data-action="upload-mode"
              ${state.startUploadMode === "link" ? "checked" : ""}
            />
            <span class="workplan-copy">
              <strong>링크 저장</strong>
              <span>결과 파일 링크만 path에 기록합니다.</span>
            </span>
          </label>
          <label class="workplan-option">
            <input
              type="radio"
              name="upload-mode"
              value="json"
              data-action="upload-mode"
              ${state.startUploadMode === "json" ? "checked" : ""}
            />
            <span class="workplan-copy">
              <strong>JSON 업로드</strong>
              <span>workingstep별 JSON 결과를 개별 dt_file로 등록합니다.</span>
            </span>
          </label>
        </div>
        ${
          state.startUploadMode === "json"
            ? '<div class="subtle">JSON 업로드는 중간 실패 시 프로젝트가 failed 처리되며, 이미 올라간 일부 dt_file은 관리자 정리가 필요할 수 있습니다.</div>'
            : ""
        }
        <button class="btn success" data-action="start-vm" ${
          detail.status === "ready" && !state.vm.actionLoading ? "" : "disabled"
        }>VM Start</button>
      </section>
    </div>
  `;
}

function renderDetailDrawer() {
  const open = state.ui.detailOpen;
  return `
    <div class="detail-drawer ${open ? "is-open" : ""}">
      <button
        type="button"
        class="drawer-backdrop"
        data-action="close-detail"
        aria-label="상세 패널 닫기"
      ></button>
      <aside class="drawer-panel">
        <div class="drawer-head">
          <div>
            <h2 class="title">Project Detail</h2>
            <div class="subtle">선택한 프로젝트의 상세 정보와 수정 가능한 항목을 보여줍니다.</div>
          </div>
          <button class="btn ghost" type="button" data-action="close-detail">닫기</button>
        </div>
        <div class="drawer-body">
          ${renderDetailPanel()}
        </div>
      </aside>
    </div>
  `;
}

function render() {
  app.innerHTML = `
    <div class="shell">
      <header class="topbar">
        <div class="brand">
          <div class="brand-mark">VM</div>
          <div class="brand-copy">
            <strong>VM Middle Console</strong>
            <span>VM 프로젝트 생성, 공정 편집, 실행 상태 확인</span>
          </div>
        </div>
        <div class="row">
          <button class="btn ghost" data-action="refresh-vm">목록 새로고침</button>
          <a class="btn ghost" href="/docs" target="_blank" rel="noreferrer">API Docs</a>
        </div>
      </header>

      <div class="notice ${state.notice ? state.notice.type : "hidden"}">
        <span>${escapeHtml(state.notice?.text || "")}</span>
        <button type="button" data-action="clear-notice">닫기</button>
      </div>

      <div class="workspace">
        <section class="panel create-panel">
          <div class="panel-head">
            <div>
              <h2 class="title">Create VM Project</h2>
              <div class="subtle">원본 프로젝트와 workplan을 선택해 새 VM 프로젝트를 생성합니다.</div>
            </div>
            <div class="segment">
              <button type="button" class="${
                state.sourceMode === "dp" ? "is-active" : ""
              }" data-action="switch-source" data-mode="dp">DP</button>
              <button type="button" class="${
                state.sourceMode === "iso" ? "is-active" : ""
              }" data-action="switch-source" data-mode="iso">ISO</button>
            </div>
          </div>
          <div class="panel-body stack">
            ${renderSourcePreview()}
            <div class="stack source-section">
              <div class="row between">
                <h3 class="section-title">Source Projects</h3>
                <button class="btn ghost" data-action="reload-source">새로고침</button>
              </div>
              ${renderSourceFilters(state.sourceMode)}
              <div class="source-list-shell">
                ${renderSourceList(state.sourceMode)}
              </div>
              ${renderSourcePager(state.sourceMode)}
            </div>
            <div class="stack">
              <h3 class="section-title">Workplans</h3>
              ${renderWorkplans()}
            </div>
            <button class="btn primary" data-action="create-vm" ${
              canCreate() ? "" : "disabled"
            }>${state.createLoading ? "생성 중..." : "VM 프로젝트 생성"}</button>
          </div>
        </section>

        <section class="panel list-panel">
          <div class="panel-head">
            <div class="row between">
              <div>
                <h2 class="title">VM Projects</h2>
                <div class="subtle">프로젝트를 선택하면 오른쪽 패널에서 상세를 확인할 수 있습니다.</div>
              </div>
              <div class="subtle">총 ${escapeHtml(state.vm.total)}개</div>
            </div>
            <form id="vm-filter-form" class="filter-bar">
              <input
                id="vm-search-input"
                class="input"
                name="q"
                value="${escapeHtml(state.vm.q)}"
                placeholder="display_name, proj_name, eid"
              />
              <select id="vm-status-select" class="select" name="status">
                <option value="">전체 상태</option>
                ${["needs-fix", "ready", "running", "completed", "failed"]
                  .map(
                    (status) => `
                      <option value="${status}" ${
                        state.vm.status === status ? "selected" : ""
                      }>${statusLabel(status)}</option>
                    `
                  )
                  .join("")}
              </select>
              <button class="btn primary" type="submit">적용</button>
              <button class="btn ghost" type="button" data-action="clear-filter">초기화</button>
            </form>
          </div>
          <div class="panel-body stack">
            ${renderVmList()}
          </div>
        </section>
      </div>
      ${renderDetailDrawer()}
    </div>
  `;

  bindEvents();
  bindThumbnailFallbacks();
}

function bindThumbnailFallbacks() {
  app.querySelectorAll("img[data-thumb-image]").forEach((img) => {
    img.addEventListener(
      "error",
      () => {
        const parent = img.closest(".thumb-frame, .project-thumb");
        if (parent) {
          parent.classList.remove("has-image");
        }
        img.remove();
      },
      { once: true }
    );
  });
}

function bindEvents() {
  const filterForm = app.querySelector("#vm-filter-form");
  if (filterForm) {
    filterForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(filterForm);
      state.vm.q = String(formData.get("q") || "");
      state.vm.status = String(formData.get("status") || "");
      state.vm.page = 1;
      try {
        await loadVmProjects({ keepSelection: false });
      } catch (error) {
        setNotice("error", error.message);
      }
    });
  }

  const sourceFilterForm = app.querySelector("#source-filter-form");
  if (sourceFilterForm) {
    sourceFilterForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(sourceFilterForm);
      state.sources.dp.q = String(formData.get("q") || "");
      state.sources.dp.page = 0;
      try {
        await loadSourceProjects("dp");
      } catch (error) {
        setNotice("error", error.message);
      }
    });
  }

  const stockTypeSelect = app.querySelector("#stock-type-select");
  if (stockTypeSelect) {
    stockTypeSelect.addEventListener("change", (event) => {
      state.editor.stockType = event.target.value;
    });
  }

  app.querySelectorAll("[data-stock-bound]").forEach((element) => {
    element.addEventListener("input", (event) => {
      const key = event.target.dataset.stockBound;
      if (key) {
        state.editor.stockBounds[key] = event.target.value;
      }
    });
  });

  app.querySelectorAll("[data-tool-field]").forEach((element) => {
    element.addEventListener("input", (event) => {
      const index = Number(event.target.dataset.index);
      const field = event.target.dataset.toolField;
      if (!Number.isNaN(index) && state.editor.process[index] && field) {
        state.editor.process[index].tool[field] = event.target.value;
      }
    });
  });

  app.querySelectorAll("[data-action='select-vm']").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        state.ui.detailOpen = true;
        await loadVmDetail(button.dataset.id);
      } catch (error) {
        setNotice("error", error.message);
      }
    });
  });

  app.querySelectorAll("[data-action='switch-source']").forEach((button) => {
    button.addEventListener("click", async () => {
      const mode = button.dataset.mode;
      if (!mode || mode === state.sourceMode) return;
      state.sourceMode = mode;
      state.selectedSourceProject = null;
      state.workplans = [];
      state.selectedWorkplan = "";
      state.sourceThumbnailKey = "";
      render();
      try {
        await ensureSourceLoaded(mode);
      } catch (error) {
        setNotice("error", error.message);
      }
    });
  });

  app.querySelectorAll("[data-action='select-source']").forEach((button) => {
    button.addEventListener("click", async () => {
      const mode = button.dataset.mode;
      const source = state.sources[mode];
      const project = source.items.find(
        (item) =>
          item.gid === button.dataset.gid &&
          item.aid === button.dataset.aid &&
          item.eid === button.dataset.eid
      );
      if (!project) return;
      try {
        await selectSourceProject(project);
      } catch (error) {
        setNotice("error", error.message);
      }
    });
  });

  app.querySelectorAll("[data-action='select-workplan']").forEach((input) => {
    input.addEventListener("change", () => {
      state.selectedWorkplan = input.value;
      render();
    });
  });

  app.querySelectorAll("[data-action='upload-mode']").forEach((input) => {
    input.addEventListener("change", () => {
      state.startUploadMode = input.value || "file";
      render();
    });
  });

  app.querySelectorAll("[data-action]").forEach((element) => {
    const action = element.dataset.action;

    if (action === "refresh-vm") {
      element.addEventListener("click", async () => {
        try {
          await loadVmProjects();
        } catch (error) {
          setNotice("error", error.message);
        }
      });
    }

    if (action === "clear-notice") {
      element.addEventListener("click", clearNotice);
    }

    if (action === "close-detail") {
      element.addEventListener("click", closeDetailDrawer);
    }

    if (action === "clear-filter") {
      element.addEventListener("click", async () => {
        state.vm.q = "";
        state.vm.status = "";
        state.vm.page = 1;
        try {
          await loadVmProjects({ keepSelection: false });
        } catch (error) {
          setNotice("error", error.message);
        }
      });
    }

    if (action === "reload-source") {
      element.addEventListener("click", async () => {
        try {
          if (state.sourceMode === "dp") {
            state.sources.dp.page = 0;
          } else {
            state.sources.iso.offset = 0;
          }
          await loadSourceProjects(state.sourceMode);
        } catch (error) {
          setNotice("error", error.message);
        }
      });
    }

    if (action === "source-prev") {
      element.addEventListener("click", async () => {
        try {
          if (state.sourceMode === "dp") {
            state.sources.dp.page = Math.max(0, state.sources.dp.page - 1);
          } else {
            state.sources.iso.offset = Math.max(
              0,
              state.sources.iso.offset - state.sources.iso.limit
            );
          }
          await loadSourceProjects(state.sourceMode);
        } catch (error) {
          setNotice("error", error.message);
        }
      });
    }

    if (action === "source-next") {
      element.addEventListener("click", async () => {
        try {
          if (state.sourceMode === "dp") {
            state.sources.dp.page += 1;
          } else {
            state.sources.iso.offset += state.sources.iso.limit;
          }
          await loadSourceProjects(state.sourceMode);
        } catch (error) {
          setNotice("error", error.message);
        }
      });
    }

    if (action === "create-vm") {
      element.addEventListener("click", createVmProject);
    }

    if (action === "clear-source-filter") {
      element.addEventListener("click", async () => {
        state.sources.dp.q = "";
        state.sources.dp.page = 0;
        try {
          await loadSourceProjects("dp");
        } catch (error) {
          setNotice("error", error.message);
        }
      });
    }

    if (action === "save-stock") {
      element.addEventListener("click", saveStock);
    }

    if (action === "save-process") {
      element.addEventListener("click", saveProcess);
    }

    if (action === "reload-detail") {
      element.addEventListener("click", async () => {
        if (!state.vm.detail?.id) return;
        try {
          await loadVmDetail(state.vm.detail.id);
        } catch (error) {
          setNotice("error", error.message);
        }
      });
    }

    if (action === "start-vm") {
      element.addEventListener("click", startVm);
    }

    if (action === "poll-vm") {
      element.addEventListener("click", pollVm);
    }

    if (action === "reset-vm") {
      element.addEventListener("click", resetVm);
    }

    if (action === "toggle-process-help") {
      element.addEventListener("click", toggleProcessHelp);
    }
  });
}

async function bootstrap() {
  render();
  try {
    await loadStocks();
    await Promise.all([loadVmProjects({ keepSelection: false }), ensureSourceLoaded("dp")]);
  } catch (error) {
    setNotice("error", error.message);
  }
}

bootstrap();
