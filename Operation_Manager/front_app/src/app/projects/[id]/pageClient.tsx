"use client";

import { useEffect, useState } from "react";
import NcEditor from "./components/NcEditor";
import MachineList from "./components/MachineList";
import NcList from "./components/NcList";
import ProductList from "./components/ProductList";
import MainButton from "./components/MainButton";

type NcData = {
  workplan_id: string;
  nc_code_id: string;
  fileName?: string | null;
  status?: string | null;
  code?: string | null;
};

export default function ProjectDetailClient({ project }: { project: { id: string; name: string } }) {
  const [ncContent, setNcContent] = useState("");
  const [selectedNc, setSelectedNc] = useState<NcData | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [originalNcContent, setOriginalNcContent] = useState("");

  const handleDeviceSelect = async (deviceId: string | null) => {
    setSelectedDeviceId(deviceId);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-white flex flex-col">
      <header className="sticky top-0 z-20 bg-white rounded-t-2xl flex items-center justify-between px-8 py-4">
        <h2 className="text-xl font-bold text-blue-700">Operation Manager – project detail</h2>
        <div>
          <span className="text-gray-400 text-sm ml-12">Project Name:</span>
          <span className="ml-2 font-semibold text-lg">{project.name}</span>
        </div>
        <MainButton />
      </header>
      <main className="flex-1 flex flex-row gap-6 px-8 py-8 overflow-hidden">
        <section className="flex-1 flex flex-col min-w-0">
          <div className="h-full overflow-y-auto">
            <NcEditor value={ncContent} onChange={setNcContent} />
          </div>
        </section>
        <section className="flex-1 flex flex-col gap-4 min-w-0">
          <div className="h-full overflow-y-auto flex flex-col gap-4">
            <NcList
              projectId={project.id}
              selectedNc={selectedNc}
              setSelectedNc={setSelectedNc}
              ncContent={ncContent}
              setNcContent={setNcContent}
              selectedDeviceId={selectedDeviceId}
              originalNcContent={originalNcContent}       // 추가
              setOriginalNcContent={setOriginalNcContent} // 추가
            />
            <MachineList onSelect={handleDeviceSelect} disabled={!selectedNc} />
            <ProductList projectId={project.id} />
          </div>
        </section>
      </main>
    </div>
  );
} 