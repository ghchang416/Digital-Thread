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
  selectedDeviceId: string | null;
  ncList: NcData[];
  setNcList: (updater: (prev: NcData[]) => NcData[]) => void;
};

export default function NcStatusMonitor({
  projectId,
  selectedDeviceId,
  ncList,
  setNcList,
}: Props) {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  useEffect(() => {
    if (!selectedDeviceId) return;

    console.log("🟡 NcStatusMonitor polling 시작됨");

    const intervalId = setInterval(async () => {
      console.log("🔁 polling 수행 중...");
      try {
        const res = await fetch(`${baseUrl}/api/projects/${projectId}/nc/status`);
        if (!res.ok) throw new Error("NC 상태 조회 실패");

        const data = await res.json(); // { filename: { deviceId: { status, upload_time } } }

        setNcList((prevList) =>
          prevList.map((nc) => {
            const filename = nc.filename || "";
            const deviceMap = data[filename];
            const entry = deviceMap?.[selectedDeviceId]; // 선택한 장비 ID에 해당하는 상태만 사용
            return {
              ...nc,
              status: entry?.status ?? "-", // 해당 장비 ID 없으면 "-"
            };
          })
        );
      } catch (err) {
        console.error("NC 상태 업데이트 실패:", err);
      }
    }, 5000);

    return () => clearInterval(intervalId);
  }, [projectId, selectedDeviceId, setNcList]);

  return null;
}