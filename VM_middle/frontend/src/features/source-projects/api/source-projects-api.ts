import { apiGet } from "@/shared/api/client";

import type {
  DpProjectListResponse,
  DpWorkplanListResponse,
  IsoProjectListResponse,
} from "@/features/source-projects/types/source-project";

export function getDpProjects(params: { page: number; size: number; q: string }) {
  const search = new URLSearchParams({
    page: String(params.page),
    size: String(params.size),
  });
  if (params.q.trim()) search.set("q", params.q.trim());
  return apiGet<DpProjectListResponse>(`/api/v1/dp/projects?${search.toString()}`);
}

export function getDpWorkplans(params: { gid: string; aid: string; eid: string }) {
  const search = new URLSearchParams({
    gid: params.gid,
    aid: params.aid,
    eid: params.eid,
  });
  return apiGet<DpWorkplanListResponse>(
    `/api/v1/dp/projects/workplans?${search.toString()}`,
  );
}

export function getIsoProjects(params: { offset: number; limit: number }) {
  const search = new URLSearchParams({
    offset: String(params.offset),
    limit: String(params.limit),
  });
  return apiGet<IsoProjectListResponse>(`/api/v1/iso-projects?${search.toString()}`);
}
