import { useEffect, useState } from "react";

type Machine = {
  id: string;
  name: string;
  vendor: string;
  code?: string;
  activate: boolean;
};

type MachineListProps = {
  onSelect: (deviceId: string | null) => void;
};

export default function MachineList({ onSelect }: MachineListProps) {

  const [devices, setDevices] = useState<Machine[]>([]);
  const [checkedId, setCheckedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const showScroll = devices.length > 4;

  //API 호출 부분
  useEffect(() => {
    async function fetchDevices() {
      setLoading(true);
      try {
        const res = await fetch("/api/machines"); // 목업 API 경로!
        if (!res.ok) throw new Error("장비 데이터를 불러오지 못했습니다.");
        const data = await res.json();
        setDevices(data.devices);
      } catch (e) {
        setDevices([]);
      }
      setLoading(false);
    }
    fetchDevices();
  }, []);

  if (loading) {
    return <div className="text-gray-400 text-center py-4">장비 목록 불러오는 중...</div>;
  }

  return (
    <div>
      <div className="font-semibold text-blue-700 mb-1">장비 리스트</div>
      <div className={`space-y-1 pr-1 ${showScroll ? "max-h-[190px] overflow-y-auto" : "max-h-none overflow-y-hidden"}`}>
        {devices.map((dev) => (
          <div
            key={dev.id}
            className="grid grid-cols-[36px_1.2fr_1.5fr_1.1fr_0.9fr] bg-white rounded-xl p-2 shadow border border-gray-100 items-center"
            style={{ minHeight: "36px" }}
          >
            {/* 체크박스 */}
            <input
              type="checkbox"
              checked={checkedId === dev.id}
              onChange={() => {
                const nextCheckedId = checkedId === dev.id ? null : dev.id;
                setCheckedId(nextCheckedId);
                onSelect(nextCheckedId); // ✅ 부모로 전달
              }}
              className={`w-4 h-4 accent-blue-500 mx-auto ${!dev.activate ? "opacity-50 cursor-not-allowed" : ""}`}
              disabled={!dev.activate}
            />
            {/* Device ID */}
            <div>
              <div className="text-[11px] text-gray-400 leading-none">Device ID</div>
              <div className="font-mono text-blue-600 text-xs truncate leading-tight">{dev.id}</div>
            </div>
            {/* Device Name */}
            <div>
              <div className="text-[11px] text-gray-400 leading-none">Device Name</div>
              <div className="font-bold text-black text-xs truncate leading-tight">{dev.name}</div>
            </div>
            {/* Vendor */}
            <div>
              <div className="text-[11px] text-gray-400 leading-none">Vendor</div>
              <div className="text-blue-500 text-xs leading-tight">{dev.vendor}</div>
            </div>
            {/* Activate */}
            <div>
              <div className="text-[11px] text-gray-400 leading-none">Activate</div>
              <div className={dev.activate ? "text-green-500 font-semibold text-xs" : "text-gray-400 text-xs"}>
                {dev.activate ? "true" : "false"}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
  
}