import { useEffect, useState } from "react";

type Machine = {
  id: string;
  name: string;
  vendorCode: string;
  toolSystem: string;
  ip_address: string;
};

type MachineListProps = {
  onSelect: (deviceId: string | null) => void;
};

export default function MachineList({ onSelect }: MachineListProps) {
  const [devices, setDevices] = useState<Machine[]>([]);
  const [checkedId, setCheckedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const showScroll = devices.length > 4;

  const fetchDevices = async () => {
    try {
      setError(false); // 초기화
      const res = await fetch(`${baseUrl}/api/machines`);
      if (!res.ok) throw new Error("장비 데이터를 불러오지 못했습니다.");
      const data = await res.json();
      setDevices(data.machines);

      // 선택된 장비가 여전히 존재하는지 확인
      const stillExists = data.machines.some((m: Machine) => m.id === checkedId);
      if (!stillExists && checkedId !== null) {
        setCheckedId(null);
        onSelect(null);
        alert("선택한 장비가 비활성화 되었습니다. 다시 선택해 주세요.");
      }
    } catch (e) {
      console.error("장비 로딩 실패:", e);
      setDevices([]);
      setError(true); // 에러 상태 설정
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices(); // 초기 1회 호출
    const intervalId = setInterval(() => {
      fetchDevices();
    }, 60000); // 1분마다 polling

    return () => clearInterval(intervalId);
  }, []);

  if (loading) {
    return <div className="text-gray-400 text-center py-4">장비 목록 불러오는 중...</div>;
  }

  return (
    <div>
      <div className="font-semibold text-blue-700 mb-1">장비 리스트</div>
      <div
        className={`space-y-1 pr-1 ${showScroll ? "max-h-[190px] overflow-y-auto" : "overflow-y-hidden"}`}
        style={{ minHeight: "152px" }}
      >
        {error ? (
          <div className="text-red-400 text-sm text-center py-2">장비를 불러오는데 실패했습니다.</div>) :
          devices.length === 0 ? (<div className="text-gray-400 text-sm text-center py-2">연결된 장비가 없습니다.</div>) : 
          (devices.map((dev) => (
          <div
            key={dev.id}
            className="flex items-center bg-white rounded-xl p-2 shadow border border-gray-100 gap-2"
            style={{ minHeight: "36px" }}
          >
            <input
              type="checkbox"
              checked={checkedId === dev.id}
              onChange={() => {
                const nextCheckedId = checkedId === dev.id ? null : dev.id;
                setCheckedId(nextCheckedId);
                onSelect(nextCheckedId);
              }}
              className="w-4 h-4 accent-blue-500 mx-2 flex-shrink-0"
            />

            <div className="min-w-[80px] max-w-[100px] flex-shrink-0">
              <div className="text-[11px] text-gray-400 leading-none">Device ID</div>
              <div className="font-mono text-blue-600 text-xs truncate leading-tight">{dev.id}</div>
            </div>

            <div className="min-w-[120px] max-w-[180px] flex-shrink-0">
              <div className="text-[11px] text-gray-400 leading-none">Device Name</div>
              <div className="font-bold text-black text-xs truncate leading-tight">{dev.name}</div>
            </div>

            <div className="min-w-[80px] max-w-[100px] flex-shrink-0">
              <div className="text-[11px] text-gray-400 leading-none">Vendor</div>
              <div className="text-blue-500 text-xs leading-tight">{dev.vendorCode}</div>
            </div>

            <div className="min-w-[120px] max-w-[160px] flex-shrink-0">
              <div className="text-[11px] text-gray-400 leading-none">IP Address</div>
              <div className="text-xs leading-tight">{dev.ip_address}</div>
            </div>

            <div className="min-w-[100px] max-w-[140px] flex-shrink-0">
              <div className="text-[11px] text-gray-400 leading-none">Tool System</div>
              <div className="text-xs leading-tight">{dev.toolSystem}</div>
            </div>
          </div>
        )))}
      </div>
    </div>
  );
}
