import { useEffect, useState } from "react";

import { useQuery } from "@tanstack/react-query";

import {
  getProcessAnnotations,
  getVmProjectDetail,
  getVmProjects,
} from "@/features/vm-projects/api/vm-projects-api";
import { SourceProjectPanel } from "@/features/source-projects/components/source-project-panel";
import { ProjectDetailDrawer } from "@/features/vm-projects/components/project-detail-drawer";
import { ProjectList } from "@/features/vm-projects/components/project-list";

import type { VmProjectListFilters } from "@/features/vm-projects/types/vm-project";

const INITIAL_FILTERS: VmProjectListFilters = {
  q: "",
  status: "",
  page: 1,
  size: 12,
};

const VM_STATUS_REFETCH_INTERVAL_MS = 5_000;

export function App() {
  const [filters, setFilters] = useState<VmProjectListFilters>(INITIAL_FILTERS);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const projectsQuery = useQuery({
    queryKey: ["vm-projects", filters],
    queryFn: () => getVmProjects(filters),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => item.status === "running")
        ? VM_STATUS_REFETCH_INTERVAL_MS
        : false,
  });

  const detailQuery = useQuery({
    queryKey: ["vm-project", selectedId],
    queryFn: () => getVmProjectDetail(selectedId!),
    enabled: Boolean(selectedId),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? VM_STATUS_REFETCH_INTERVAL_MS : false,
  });

  const annotationsQuery = useQuery({
    queryKey: ["vm-project", selectedId, "process-annotations"],
    queryFn: () => getProcessAnnotations(selectedId!),
    enabled: Boolean(selectedId),
  });

  useEffect(() => {
    if (!selectedId && projectsQuery.data?.items.length) {
      setSelectedId(projectsQuery.data.items[0].id);
    }
  }, [projectsQuery.data?.items, selectedId]);

  const errorMessage =
    projectsQuery.error instanceof Error ? projectsQuery.error.message : null;
  const detailErrorMessage =
    detailQuery.error instanceof Error ? detailQuery.error.message : null;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            VM
          </span>
          <div>
            <h1>VM Middle Console</h1>
            <p>Digital Thread project to Virtual Machining execution</p>
          </div>
        </div>
        <nav className="topbar__actions" aria-label="보조 링크">
          <a href="/docs" target="_blank" rel="noreferrer">
            API Docs
          </a>
          <a href="/healthz" target="_blank" rel="noreferrer">
            Health
          </a>
        </nav>
      </header>

      <main className="workspace">
        <SourceProjectPanel
          onCreated={(id) => {
            if (id) setSelectedId(id);
            setIsDrawerOpen(true);
          }}
        />

        <ProjectList
          items={projectsQuery.data?.items ?? []}
          filters={filters}
          selectedId={selectedId}
          total={projectsQuery.data?.total ?? 0}
          isLoading={projectsQuery.isLoading}
          errorMessage={errorMessage}
          onFiltersChange={setFilters}
          onSelect={(id) => {
            setSelectedId(id);
            setIsDrawerOpen(true);
          }}
        />
      </main>

      <ProjectDetailDrawer
        detail={detailQuery.data ?? null}
        annotations={annotationsQuery.data?.items ?? []}
        isOpen={isDrawerOpen}
        isLoading={detailQuery.isLoading || annotationsQuery.isLoading}
        errorMessage={detailErrorMessage}
        onClose={() => setIsDrawerOpen(false)}
      />
    </div>
  );
}
