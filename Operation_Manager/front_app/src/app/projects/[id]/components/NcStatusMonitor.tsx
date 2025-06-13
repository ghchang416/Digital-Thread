"use client";

import { useEffect } from "react";

type NcData = {
  workplan_id: string;
  nc_code_id: string;
  filename?: string | null;
  status?: string | null;
  code?: string | null;
};

type Props = {
  projectId: string;
  ncList: NcData[];
  setNcList: (updater: (prev: NcData[]) => NcData[]) => void;
  selectedDeviceId: string | null;
};

export default function NcStatusMonitor({
  projectId,
  selectedDeviceId,
  ncList,
  setNcList,
}: Props & { selectedDeviceId: string | null }) {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  useEffect(() => {
    if (!selectedDeviceId) return;

    console.log("🟡 NcStatusMonitor polling 시작됨");

    const intervalId = setInterval(async () => {
      const pendingList = ncList.filter((nc) => nc.status === "가공대기");
      if (pendingList.length === 0) return;

      try {

        console.log("polling 진행중");
        const res = await fetch(`${baseUrl}/api/projects/${projectId}/nc/status`);
        if (!res.ok) throw new Error("NC 상태 조회 실패");
        const data = await res.json();

        setNcList((prevList) =>
          prevList.map((nc) => {
            const filename = nc.filename || "";
            const deviceMap = data[filename];
            if (!deviceMap || !deviceMap[selectedDeviceId]) return nc;

            const updatedEntry = deviceMap[selectedDeviceId];
            return {
              ...nc,
              status: updatedEntry.status,
            };
          })
        );
      } catch (err) {
        console.error("NC 상태 업데이트 실패:", err);
      }
    }, 5000);

    return () => clearInterval(intervalId);
  }, [projectId, selectedDeviceId, ncList, setNcList]);

  return null;

}