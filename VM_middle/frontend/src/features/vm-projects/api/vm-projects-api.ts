import { apiGet, apiPatch, apiPost } from "@/shared/api/client";

import type {
  PollVmResponse,
  ProcessPatchPayload,
  ProcessAnnotationsResponse,
  ProjectFile,
  ResetVmResponse,
  StartVmPayload,
  StartVmResponse,
  StockItemsResponse,
  StockPatchPayload,
  VmProjectDetail,
  VmProjectCreatePayload,
  VmProjectCreateResponse,
  VmProjectListFilters,
  VmProjectListResponse,
} from "@/features/vm-projects/types/vm-project";

const VM_PROJECTS_BASE = "/api/v1/vm-project";

export function getVmProjects(filters: VmProjectListFilters) {
  const params = new URLSearchParams({
    page: String(filters.page),
    size: String(filters.size),
  });

  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.status) params.set("status", filters.status);

  return apiGet<VmProjectListResponse>(`${VM_PROJECTS_BASE}?${params.toString()}`);
}

export function getVmProjectDetail(id: string) {
  return apiGet<VmProjectDetail>(`${VM_PROJECTS_BASE}/${encodeURIComponent(id)}`);
}

export function getProcessAnnotations(id: string) {
  return apiGet<ProcessAnnotationsResponse>(
    `${VM_PROJECTS_BASE}/${encodeURIComponent(id)}/process-annotations`,
  );
}

export function getStockItems(q = "") {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiGet<StockItemsResponse>(`${VM_PROJECTS_BASE}/stocks${suffix}`);
}

export function patchVmProjectStock(id: string, payload: StockPatchPayload) {
  return apiPatch<ProjectFile, StockPatchPayload>(
    `${VM_PROJECTS_BASE}/${encodeURIComponent(id)}/project-file/stock`,
    payload,
  );
}

export function patchVmProjectProcess(id: string, payload: ProcessPatchPayload) {
  return apiPatch<ProjectFile, ProcessPatchPayload>(
    `${VM_PROJECTS_BASE}/${encodeURIComponent(id)}/project-file/process`,
    payload,
  );
}

export function startVmProject(id: string, payload: StartVmPayload) {
  return apiPost<StartVmResponse, StartVmPayload>(
    `${VM_PROJECTS_BASE}/${encodeURIComponent(id)}/start-vm`,
    payload,
  );
}

export function pollVmProject(id: string) {
  return apiPost<PollVmResponse, Record<string, never>>(
    `${VM_PROJECTS_BASE}/${encodeURIComponent(id)}/poll`,
    {},
  );
}

export function resetVmProject(id: string) {
  return apiPost<ResetVmResponse, Record<string, never>>(
    `${VM_PROJECTS_BASE}/${encodeURIComponent(id)}/reset`,
    {},
  );
}

export function getVmProjectThumbnailUrl(id: string) {
  return `${VM_PROJECTS_BASE}/${encodeURIComponent(id)}/thumbnail`;
}

export function createVmProject(payload: VmProjectCreatePayload) {
  return apiPost<VmProjectCreateResponse, VmProjectCreatePayload>(
    VM_PROJECTS_BASE,
    payload,
  );
}
