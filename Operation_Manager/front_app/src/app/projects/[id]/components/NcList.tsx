import { useEffect, useState } from "react";
import ActionButton from "./ActionButton";
import NcStatusMonitor from "./NcStatusMonitor";

type NcData = {
  workplan_id: string;
  nc_code_id: string;
  filename?: string | null;
  status?: string | null;
  code?: string | null;
};

export default function NcList({
  projectId,
  selectedNc,
  selectedDeviceId,
  setSelectedNc,
  ncContent,
  setNcContent,
  originalNcContent,
  setOriginalNcContent,
}: {
  projectId: string;
  selectedNc: NcData | null;
  selectedDeviceId: string | null;
  setSelectedNc: (nc: NcData | null) => void;
  ncContent: string;
  setNcContent: (content: string) => void;
  originalNcContent: string;
  setOriginalNcContent: (content: string) => void;
}) {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const [ncList, setNcList] = useState<NcData[]>([]);
  const [loadingNc, setLoadingNc] = useState(false);
  const [error, setError] = useState(false);

  const fetchNcList = async (preserveSelected = false) => {
    try {
      setError(false);
      const res = await fetch(`${baseUrl}/api/projects/${projectId}/workplans`);
      if (!res.ok) throw new Error("API 요청 실패");
      const data = await res.json();
      if (Array.isArray(data.results)) {
        setNcList(data.results);
        if (preserveSelected && selectedNc) {
          const match = data.results.find((nc: NcData) => nc.workplan_id === selectedNc.workplan_id);
          setSelectedNc(match || null);
        }
      } else {
        setNcList([]);
      }
    } catch (error) {
      console.error("NC 리스트 가져오기 실패:", error);
      setError(true);
      setNcList([]);
    }
  };

  const handleCheck = async (nc: NcData) => {
    const isSame = selectedNc?.nc_code_id === nc.nc_code_id;
    const nextNc = isSame ? null : nc;
    setSelectedNc(nextNc);

    if (!isSame && nc.workplan_id && nc.nc_code_id) {
      setNcContent("로딩 중...");
      try {
        setLoadingNc(true);
        const res = await fetch(
          `${baseUrl}/api/projects/${projectId}/workplans/${nc.workplan_id}/nc/${nc.nc_code_id}`
        );
        const data = await res.json();
        setNcContent(data.content || "");
        setOriginalNcContent(data.content || "");  // 불러온 원본 저장
      } catch (e) {
        alert("NC 코드 불러오기 실패");
        setNcContent("");
        setOriginalNcContent("");
      } finally {
        setLoadingNc(false);
      }
    } else {
      setNcContent("");
      setOriginalNcContent("");
    }
  };

  const handleSave = async () => {
    if (!selectedNc) return;
    const url = `${baseUrl}/api/projects/${projectId}/workplans/${selectedNc.workplan_id}/nc/${selectedNc.nc_code_id}`;
    try {
      const res = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: ncContent }),
      });

      console.log(res);
      if (!res.ok) throw new Error("저장 실패");
      alert("파일이 서버에 저장되었습니다.");
      await fetchNcList(true);
    } catch (e) {
      alert("저장 중 오류 발생");
    }
  };

  const handleSend = async () => {
    if (!selectedNc || !selectedDeviceId) return;

    const url = `${baseUrl}/api/machines/${selectedDeviceId}/send_nc?project_id=${projectId}&nc_id=${selectedNc.nc_code_id}`;

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      const result = await res.json();

      if (!res.ok) {
        if (res.status === 400 && result?.detail) {
          alert(`전송 실패: ${result.detail}`);
        } else {
          alert("장비 전송 중 오류가 발생했습니다.");
        }
        console.error("장비 전송 실패:", result);
        return;
      }

      alert("장비로 전송되었습니다.");
    } catch (error) {
      console.error("장비 전송 예외 발생:", error);
      alert("장비 전송 중 네트워크 오류가 발생했습니다.");
    }
  };

  useEffect(() => {
    fetchNcList();
  }, [projectId]);

  useEffect(() => {
    const updateStatusOnDeviceChange = async () => {
      if (!selectedDeviceId) {
        setNcList((prevList) =>
          prevList.map((nc) => ({
            ...nc,
            status: "-",
          }))
        );
        return;
      }

      try {
        const res = await fetch(`${baseUrl}/api/projects/${projectId}/nc/status`);
        if (!res.ok) throw new Error("NC 상태 초기화 실패");
        const data = await res.json();

        setNcList((prevList) =>
          prevList.map((nc) => {
            const filename = nc.filename || "";
            const deviceMap = data[filename];
            const entry = deviceMap?.[selectedDeviceId];
            return {
              ...nc,
              status: entry?.status ?? "-",
            };
          })
        );
      } catch (err) {
        console.error("🟥 NC 상태 캐시 초기화 실패:", err);
      }
    };

    updateStatusOnDeviceChange();
  }, [selectedDeviceId]);

  const showScroll = ncList.length > 4;
  const containerClassName =
    "space-y-1 pr-1" +
    (showScroll ? " max-h-[190px] overflow-y-auto" : " max-h-none overflow-y-hidden") +
    (loadingNc ? " opacity-50 pointer-events-none" : "");

  return (
    <div>
      <NcStatusMonitor
        projectId={projectId}
        ncList={ncList}
        setNcList={setNcList}
        selectedDeviceId={selectedDeviceId} />

      <div className="font-semibold text-blue-700 mb-1">NC List</div>
      <div className={containerClassName} style={{ minHeight: "152px" }}>
        {error ? (
          <div className="text-red-400 text-sm text-center py-2">NC를 불러오는데 실패했습니다.</div>
        ) : ncList.length === 0 ? (
          <div className="text-gray-400 text-sm text-center py-2">NC가 없습니다.</div>
        ) : (
          ncList.map((nc) => (
            <div
              key={nc.workplan_id}
              className="flex items-center bg-white rounded-xl p-2 shadow border border-gray-100 gap-2"
              style={{ minHeight: "36px" }}
            >
              <input
                type="checkbox"
                checked={selectedNc?.nc_code_id === nc.nc_code_id}
                onChange={() => handleCheck(nc)}
                className="w-4 h-4 accent-blue-500 mx-2 flex-shrink-0"
              />
              <div className="min-w-[100px] max-w-[140px] flex-shrink-0">
                <div className="text-[11px] text-gray-400 leading-none">Workplan</div>
                <div className="font-bold text-black text-xs truncate leading-tight">{nc.workplan_id}</div>
              </div>
              <div className="min-w-[180px] max-w-[280px] flex-shrink-0">
                <div className="text-[11px] text-gray-400 leading-none">NC Code ID</div>
                <div className="font-mono text-blue-600 text-xs truncate leading-tight">{nc.nc_code_id}</div>
              </div>
              <div className="min-w-[120px] max-w-[140px] flex-shrink-0">
                <div className="text-[11px] text-gray-400 leading-none">File Name</div>
                <div className="text-xs leading-tight">{nc.filename || "-"}</div>
              </div>
              <div className="min-w-[140px] max-w-[170px] flex-shrink-0">
                <div className="text-[11px] text-gray-400 leading-none">Status</div>
                <div className="text-xs leading-tight">{nc.status || "-"}</div>
              </div>
            </div>
          ))
        )}
      </div>
      <div className="flex justify-end gap-2 mt-2">
        <ActionButton
          color="gray"
          onClick={handleSave}
          disabled={!selectedNc || loadingNc || ncContent === originalNcContent}
        >저장
        </ActionButton>
        <ActionButton color="blue" onClick={handleSend} disabled={!selectedNc || loadingNc || !selectedDeviceId}>장비전송</ActionButton>
      </div>
    </div>
  );
}
