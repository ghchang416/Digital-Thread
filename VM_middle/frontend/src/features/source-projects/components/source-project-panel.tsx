import { useEffect, useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2, Search } from "lucide-react";

import {
  getDpProjects,
  getDpWorkplans,
  getIsoProjects,
} from "@/features/source-projects/api/source-projects-api";
import { createVmProject } from "@/features/vm-projects/api/vm-projects-api";

import type {
  SourceMode,
  SourceProject,
  SourceWorkplan,
} from "@/features/source-projects/types/source-project";
import type { VmProjectCreatePayload } from "@/features/vm-projects/types/vm-project";

const DP_PAGE_SIZE = 10;
const ISO_PAGE_SIZE = 20;

interface SourceProjectPanelProps {
  onCreated: (vmProjectId: string | null) => void;
}

export function SourceProjectPanel({ onCreated }: SourceProjectPanelProps) {
  const queryClient = useQueryClient();
  const [sourceMode, setSourceMode] = useState<SourceMode>("dp");
  const [dpSearchDraft, setDpSearchDraft] = useState("");
  const [dpSearch, setDpSearch] = useState("");
  const [dpPage, setDpPage] = useState(0);
  const [isoOffset, setIsoOffset] = useState(0);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedWorkplan, setSelectedWorkplan] = useState("");

  const dpProjectsQuery = useQuery({
    queryKey: ["source-projects", "dp", dpPage, DP_PAGE_SIZE, dpSearch],
    queryFn: () => getDpProjects({ page: dpPage, size: DP_PAGE_SIZE, q: dpSearch }),
    enabled: sourceMode === "dp",
  });

  const isoProjectsQuery = useQuery({
    queryKey: ["source-projects", "iso", isoOffset, ISO_PAGE_SIZE],
    queryFn: () => getIsoProjects({ offset: isoOffset, limit: ISO_PAGE_SIZE }),
    enabled: sourceMode === "iso",
  });

  const projects = useMemo(() => {
    if (sourceMode === "dp") {
      return (dpProjectsQuery.data?.items ?? []).map<SourceProject>((item) => ({
        source: "dp",
        gid: item.gid,
        aid: item.aid,
        eid: item.eid,
        displayName: item.display_name,
        description: item.description,
        assetType: item.asset_type,
      }));
    }

    return (isoProjectsQuery.data?.items ?? []).map<SourceProject>((item) => ({
      source: "iso",
      gid: item.gid,
      aid: item.aid,
      eid: item.eid,
      displayName: item.name,
      description: item.description,
      assetType: item.type,
      mainWpid: item.main_wpid,
      workplanIds: item.wpid,
    }));
  }, [dpProjectsQuery.data?.items, isoProjectsQuery.data?.items, sourceMode]);

  const selectedProject = useMemo(
    () => projects.find((project) => sourceProjectKey(project) === selectedKey) ?? null,
    [projects, selectedKey],
  );

  const dpWorkplansQuery = useQuery({
    queryKey: [
      "source-projects",
      "dp",
      "workplans",
      selectedProject?.gid,
      selectedProject?.aid,
      selectedProject?.eid,
    ],
    queryFn: () =>
      getDpWorkplans({
        gid: selectedProject!.gid,
        aid: selectedProject!.aid,
        eid: selectedProject!.eid,
      }),
    enabled: sourceMode === "dp" && Boolean(selectedProject),
  });

  const workplans = useMemo<SourceWorkplan[]>(() => {
    if (!selectedProject) return [];
    if (selectedProject.source === "dp") {
      return (dpWorkplansQuery.data?.workplans ?? []).map((item) => ({
        wpid: item.wpid,
        wsCount: item.ws_count,
        pattern: item.pattern,
      }));
    }

    const ids = selectedProject.workplanIds ?? [];
    if (ids.length > 0) {
      return ids.map((wpid) => ({ wpid, wsCount: null, pattern: "ISO" }));
    }
    if (selectedProject.mainWpid) {
      return [{ wpid: selectedProject.mainWpid, wsCount: null, pattern: "ISO" }];
    }
    return [];
  }, [dpWorkplansQuery.data?.workplans, selectedProject]);

  useEffect(() => {
    if (projects.length === 0) {
      setSelectedKey(null);
      return;
    }
    if (!selectedKey || !projects.some((project) => sourceProjectKey(project) === selectedKey)) {
      setSelectedKey(sourceProjectKey(projects[0]));
    }
  }, [projects, selectedKey]);

  useEffect(() => {
    setSelectedWorkplan(workplans[0]?.wpid ?? "");
  }, [selectedKey, workplans]);

  const createMutation = useMutation({
    mutationFn: (payload: VmProjectCreatePayload) => createVmProject(payload),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["vm-projects"] });
      onCreated(result.vm_project_id ?? result.id ?? null);
    },
  });

  const isProjectsLoading =
    sourceMode === "dp" ? dpProjectsQuery.isLoading : isoProjectsQuery.isLoading;
  const projectsError =
    sourceMode === "dp" ? dpProjectsQuery.error : isoProjectsQuery.error;
  const workplansError = dpWorkplansQuery.error;
  const canCreate =
    Boolean(selectedProject) &&
    !createMutation.isPending &&
    !dpWorkplansQuery.isFetching &&
    (workplans.length === 0 || Boolean(selectedWorkplan));

  return (
    <section className="panel panel--create" aria-labelledby="create-heading">
      <div className="panel__header">
        <div>
          <h2 id="create-heading">Create VM Project</h2>
          <p>원본 프로젝트와 workplan을 선택해 VM 프로젝트를 생성합니다.</p>
        </div>
        <div className="segmented-control" aria-label="source 선택">
          <button
            type="button"
            className={sourceMode === "dp" ? "is-active" : ""}
            onClick={() => {
              setSourceMode("dp");
              setSelectedKey(null);
            }}
          >
            DP
          </button>
          <button
            type="button"
            className={sourceMode === "iso" ? "is-active" : ""}
            onClick={() => {
              setSourceMode("iso");
              setSelectedKey(null);
            }}
          >
            ISO
          </button>
        </div>
      </div>

      <div className="source-panel-body">
        {sourceMode === "dp" ? (
          <form
            className="source-search"
            onSubmit={(event) => {
              event.preventDefault();
              setDpPage(0);
              setDpSearch(dpSearchDraft);
            }}
          >
            <label className="field field--search">
              <span className="sr-only">DP 프로젝트 검색</span>
              <Search aria-hidden="true" size={16} />
              <input
                value={dpSearchDraft}
                placeholder="DP 프로젝트 검색"
                onChange={(event) => setDpSearchDraft(event.target.value)}
              />
            </label>
            <button className="button button--primary" type="submit">
              검색
            </button>
          </form>
        ) : null}

        <div className="source-list" aria-busy={isProjectsLoading}>
          {isProjectsLoading ? <SourceListSkeleton /> : null}
          {!isProjectsLoading && projectsError instanceof Error ? (
            <div className="empty-state empty-state--error">
              <strong>소스 프로젝트를 불러오지 못했습니다.</strong>
              <span>{projectsError.message}</span>
            </div>
          ) : null}
          {!isProjectsLoading && !projectsError && projects.length === 0 ? (
            <div className="empty-state">
              <strong>표시할 프로젝트가 없습니다.</strong>
              <span>검색어나 페이지를 조정해 보세요.</span>
            </div>
          ) : null}
          {!isProjectsLoading && !projectsError
            ? projects.map((project) => (
                <button
                  type="button"
                  key={sourceProjectKey(project)}
                  className={`source-row ${
                    sourceProjectKey(project) === selectedKey ? "source-row--selected" : ""
                  }`}
                  onClick={() => setSelectedKey(sourceProjectKey(project))}
                >
                  <strong>{project.displayName || project.eid}</strong>
                  <span>{project.eid}</span>
                  <span>{project.assetType || project.source.toUpperCase()}</span>
                </button>
              ))
            : null}
        </div>

        <SourcePager
          sourceMode={sourceMode}
          dpPage={dpPage}
          dpTotal={dpProjectsQuery.data?.total ?? 0}
          isoOffset={isoOffset}
          isoTotal={isoProjectsQuery.data?.total ?? 0}
          isoHasMore={Boolean(isoProjectsQuery.data?.has_more)}
          onDpPageChange={setDpPage}
          onIsoOffsetChange={setIsoOffset}
        />

        <div className="workplan-box">
          <div className="workplan-box__header">
            <strong>Workplans</strong>
            {dpWorkplansQuery.isFetching ? (
              <span className="loading-inline">
                <Loader2 aria-hidden="true" size={14} />
                조회 중
              </span>
            ) : null}
          </div>
          {!selectedProject ? (
            <div className="inline-note">프로젝트를 선택하면 workplan 목록이 표시됩니다.</div>
          ) : null}
          {selectedProject && workplansError instanceof Error ? (
            <div className="empty-state empty-state--error">
              <strong>workplan 조회 실패</strong>
              <span>{workplansError.message}</span>
            </div>
          ) : null}
          {selectedProject && !workplansError && !dpWorkplansQuery.isFetching && workplans.length === 0 ? (
            <div className="inline-note">선택 가능한 workplan이 없습니다. wpid 없이 생성합니다.</div>
          ) : null}
          {workplans.length > 0 ? (
            <div className="workplan-list" role="radiogroup" aria-label="workplan 선택">
              {workplans.map((workplan, index) => (
                <label className="workplan-option" key={`${workplan.wpid ?? "none"}-${index}`}>
                  <input
                    type="radio"
                    name="source-workplan"
                    value={workplan.wpid ?? ""}
                    checked={(workplan.wpid ?? "") === selectedWorkplan}
                    onChange={() => setSelectedWorkplan(workplan.wpid ?? "")}
                  />
                  <span>
                    <strong>{workplan.wpid || `workplan-${index + 1}`}</strong>
                    <small>
                      {workplan.pattern} / WS {workplan.wsCount ?? "-"}
                    </small>
                  </span>
                </label>
              ))}
            </div>
          ) : null}
        </div>

        {createMutation.error instanceof Error ? (
          <div className="empty-state empty-state--error">
            <strong>VM 프로젝트 생성 실패</strong>
            <span>{createMutation.error.message}</span>
          </div>
        ) : null}
        {createMutation.isSuccess ? (
          <div className="inline-note inline-note--success">
            VM 프로젝트를 생성했습니다. 목록과 상세 패널을 갱신합니다.
          </div>
        ) : null}

        <button
          className="button button--primary button--full"
          type="button"
          disabled={!canCreate}
          onClick={() => {
            if (!selectedProject) return;
            const payload: VmProjectCreatePayload = {
              source: selectedProject.source,
              gid: selectedProject.gid,
              aid: selectedProject.aid,
              eid: selectedProject.eid,
            };
            if (selectedWorkplan) payload.wpid = selectedWorkplan;
            createMutation.mutate(payload);
          }}
        >
          {createMutation.isPending ? "생성 중..." : "VM 프로젝트 생성"}
        </button>
      </div>
    </section>
  );
}

function sourceProjectKey(project: SourceProject) {
  return `${project.source}|${project.gid}|${project.aid}|${project.eid}`;
}

function SourceListSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, index) => (
        <div className="source-row source-row--skeleton" key={index}>
          <span className="skeleton skeleton--line" />
          <span className="skeleton skeleton--line short" />
        </div>
      ))}
    </>
  );
}

interface SourcePagerProps {
  sourceMode: SourceMode;
  dpPage: number;
  dpTotal: number;
  isoOffset: number;
  isoTotal: number;
  isoHasMore: boolean;
  onDpPageChange: (page: number) => void;
  onIsoOffsetChange: (offset: number) => void;
}

function SourcePager({
  sourceMode,
  dpPage,
  dpTotal,
  isoOffset,
  isoTotal,
  isoHasMore,
  onDpPageChange,
  onIsoOffsetChange,
}: SourcePagerProps) {
  const dpPageCount = Math.max(1, Math.ceil(dpTotal / DP_PAGE_SIZE));
  const isoPage = Math.floor(isoOffset / ISO_PAGE_SIZE) + 1;
  const isoPageCount = Math.max(1, Math.ceil(isoTotal / ISO_PAGE_SIZE));

  if (sourceMode === "dp") {
    return (
      <div className="source-pager">
        <button
          className="icon-button"
          type="button"
          aria-label="이전 DP 프로젝트 페이지"
          disabled={dpPage === 0}
          onClick={() => onDpPageChange(Math.max(0, dpPage - 1))}
        >
          <ChevronLeft aria-hidden="true" size={16} />
        </button>
        <span>
          {dpPage + 1} / {dpPageCount}
        </span>
        <button
          className="icon-button"
          type="button"
          aria-label="다음 DP 프로젝트 페이지"
          disabled={dpPage + 1 >= dpPageCount}
          onClick={() => onDpPageChange(dpPage + 1)}
        >
          <ChevronRight aria-hidden="true" size={16} />
        </button>
      </div>
    );
  }

  return (
    <div className="source-pager">
      <button
        className="icon-button"
        type="button"
        aria-label="이전 ISO 프로젝트 페이지"
        disabled={isoOffset === 0}
        onClick={() => onIsoOffsetChange(Math.max(0, isoOffset - ISO_PAGE_SIZE))}
      >
        <ChevronLeft aria-hidden="true" size={16} />
      </button>
      <span>
        {isoPage} / {isoPageCount}
      </span>
      <button
        className="icon-button"
        type="button"
        aria-label="다음 ISO 프로젝트 페이지"
        disabled={!isoHasMore}
        onClick={() => onIsoOffsetChange(isoOffset + ISO_PAGE_SIZE)}
      >
        <ChevronRight aria-hidden="true" size={16} />
      </button>
    </div>
  );
}
