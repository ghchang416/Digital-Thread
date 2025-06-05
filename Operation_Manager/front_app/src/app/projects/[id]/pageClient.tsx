"use client";

import NcEditor from "./components/NcEditor";
import DeviceList from "./components/MachineList";
import NcList from "./components/NcList";
import ProductList from "./components/ProductList";
import MainButton from "./components/MainButton";

import { useEffect, useState } from "react";

type Props = {
  project : { 
    id : string;
    name : string;
  }
}

export default function ProjectDetailClient({ project }: Props) {
  
  const [ncCode, setNcCode] = useState(""); // 현재 선택된 NC 코드 문자열
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null); //장비 선택 상태 추가

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-white flex flex-col">
      {/* 헤더 (sticky, 그림자+여백, 항상 상단) */}
      <header className="sticky top-0 z-20 bg-white rounded-t-2xl flex items-center justify-between px-8 py-4">
        <h2 className="text-xl font-bold text-blue-700">Operation Manager – project detail</h2>
        <div>
          <span className="text-gray-400 text-sm ml-12">Project Name:</span>
          <span className="ml-2 font-semibold text-lg">{project.name}</span>
        </div>
        <MainButton />
      </header>
      {/* 본문: 스크롤 가능한 flex 레이아웃 */}
      <main className="flex-1 flex flex-row gap-6 px-8 py-8 overflow-hidden">
        {/* 좌측: 에디터 (가변 높이, 내부 스크롤) */}
        <section className="flex-1 flex flex-col min-w-0">
          <div className="h-full overflow-y-auto">
            <NcEditor ncCode={ncCode} />
          </div>
        </section>
        {/* 우측: 리스트들 (가변 높이, 내부 스크롤) */}
        <section className="flex-1 flex flex-col gap-4 min-w-0">
          <div className="h-full overflow-y-auto flex flex-col gap-4">
            <DeviceList onSelect={(id) => setSelectedDeviceId(id)} />
            <NcList onSelectNc={setNcCode} isDeviceSelected={selectedDeviceId !== null} />
            <ProductList />
          </div>
        </section>
      </main>
    </div>
  );
}