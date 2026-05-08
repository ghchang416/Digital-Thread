export type SourceMode = "dp" | "iso";

export interface SourceProject {
  source: SourceMode;
  gid: string;
  aid: string;
  eid: string;
  displayName: string | null;
  description: string | null;
  assetType: string | null;
  mainWpid?: string | null;
  workplanIds?: string[];
}

export interface DpProjectItem {
  gid: string;
  aid: string;
  eid: string;
  display_name: string | null;
  description: string | null;
  asset_type: string | null;
}

export interface DpProjectListResponse {
  items: DpProjectItem[];
  total: number;
  page: number;
  size: number;
}

export interface DpWorkplanItem {
  wpid: string | null;
  ws_count: number;
  pattern: string;
}

export interface DpWorkplanListResponse {
  gid: string;
  aid: string;
  eid: string;
  workplans: DpWorkplanItem[];
}

export interface IsoProjectItem {
  gid: string;
  aid: string;
  eid: string;
  name: string | null;
  type: string | null;
  description: string | null;
  main_wpid: string | null;
  wpid: string[];
}

export interface IsoProjectListResponse {
  items: IsoProjectItem[];
  has_more: boolean;
  next_offset: number | null;
  total: number;
}

export interface SourceWorkplan {
  wpid: string | null;
  wsCount: number | null;
  pattern: string;
}
