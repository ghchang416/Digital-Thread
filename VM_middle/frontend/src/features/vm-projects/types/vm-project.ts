export type VmProjectStatus =
  | "needs-fix"
  | "ready"
  | "running"
  | "completed"
  | "failed";

export interface VmProjectListItem {
  id: string;
  status: VmProjectStatus;
  source: string;
  proj_name: string | null;
  display_name: string | null;
  gid: string;
  aid: string;
  eid: string;
  wpid: string | null;
  created_at: string;
  updated_at: string;
  validation_is_valid: boolean | null;
  validation_error_count: number;
}

export interface VmProjectListResponse {
  total: number;
  page: number;
  size: number;
  has_more: boolean;
  items: VmProjectListItem[];
}

export interface ProjectFileProcess {
  file_path: string | null;
  output_dir_path: string | null;
  tool_data: string | null;
}

export interface ProjectFile {
  stock_type: string | null;
  stock_size: string | null;
  process_count: number;
  process: ProjectFileProcess[];
}

export interface VmResultUpload {
  mode: string | null;
  seq_id: number | null;
  total_count: number;
  uploaded_indices: number[];
  uploaded_element_ids: string[];
  last_uploaded_index: number | null;
  last_uploaded_element_id: string | null;
  failed_index: number | null;
  error_message: string | null;
  updated_at: string | null;
}

export interface VmProjectDetail {
  id: string;
  status: VmProjectStatus;
  source: string;
  proj_name: string | null;
  display_name: string | null;
  gid: string;
  aid: string;
  eid: string;
  wpid: string | null;
  created_at: string;
  updated_at: string;
  latest_files: Record<string, string>;
  validation_is_valid: boolean | null;
  validation_errors: string[];
  vm_job_id: string | null;
  vm_last_polled_at: string | null;
  vm_error_message: string | null;
  vm_raw_status: string | null;
  upload_mode: string | null;
  vm_result_upload: VmResultUpload | null;
  project_file_draft: ProjectFile;
}

export interface ProcessAnnotationItem {
  index: number;
  workingstep_id: string | null;
  tool_element_id: string | null;
}

export interface ProcessAnnotationsResponse {
  items: ProcessAnnotationItem[];
}

export interface VmProjectListFilters {
  q: string;
  status: VmProjectStatus | "";
  page: number;
  size: number;
}

export interface StockPatchPayload {
  stock_type?: string;
  stock_size?: string;
}

export interface ProcessPatchPayload {
  process: ProjectFileProcess[];
}

export type VmUploadMode = "file" | "link" | "json";

export interface StartVmPayload {
  upload_mode: VmUploadMode;
}

export interface StartVmResponse {
  vm_project_id: string;
  status: VmProjectStatus;
  vm_job_id: string;
  vm_state: string | null;
}

export interface PollVmResponse {
  vm_project_id: string;
  status: VmProjectStatus;
  vm_state: string | null;
}

export interface ResetVmResponse {
  vm_project_id: string;
  status: VmProjectStatus;
}

export interface StockItem {
  code: string;
  name: string;
}

export interface StockItemsResponse {
  items: StockItem[];
}

export type VmProjectSource = "dp" | "iso";

export interface VmProjectCreatePayload {
  source: VmProjectSource;
  gid: string;
  aid: string;
  eid: string;
  wpid?: string;
}

export interface VmProjectCreateResponse {
  vm_project_id?: string;
  id?: string;
  status: VmProjectStatus;
  validation?: {
    is_valid: boolean;
    errors: string[];
  };
}
