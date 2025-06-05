"use client";

import { useEffect , useState } from "react";
import ActionButton from "./ActionButton"; // 저장/장비전송용 공통 버튼
import NcStatusMonitor from "./NcStatusMonitor";

type NcData = {
  id: string;
  workplan: string;
  fileName: string;
  status: string;
  code: string;
};


type NcListProps = {
  onSelectNc: (code: string) => void; // 선택된 NC 코드를 왼쪽에 반영하는 콜백
  isDeviceSelected: boolean;
};


export default function NcList({ onSelectNc, isDeviceSelected }: NcListProps) {
  const [ncList, setNcList] = useState<NcData[]>([]);
  const [checkedId, setCheckedId] = useState<string | null>(null);

  const showScroll = ncList.length > 4;

  //API 호출 부분
  useEffect(() => {
    const fetchNcList = async () => {
      const res = await fetch("/api/nc");
      const data = await res.json();
      setNcList(data);
    };
    fetchNcList();
  }, []);

  useEffect(() => {
    if (!isDeviceSelected) {
      setCheckedId(null);
      onSelectNc("");
    }
  }, [isDeviceSelected]);

  const selectedNc = ncList.find((n) => n.id === checkedId);
  const isSendingDisabled = selectedNc?.status === "가공중";

  // 저장 버튼 클릭
  const handleSave = async () => {
    if (!selectedNc) return;

    // 1. 서버에 저장 요청
    await fetch("/api/save-nc", {
      method: "POST",
      body: JSON.stringify(selectedNc),
      headers: { "Content-Type": "application/json" },
    });

    // 2. 최신 상태 재조회
    const res = await fetch(`/api/nc/${selectedNc.id}`);
    const updated = await res.json();

    // 3. 리스트 갱신
    setNcList((prev) =>
      prev.map((item) => (item.id === updated.id ? { ...item, status: updated.status } : item))
    );

    alert("파일이 서버에 저장되었습니다.");
  };

  // 장비 전송 버튼 클릭
  const handleSend = async () => {
    if (!selectedNc) return;

    await fetch("/api/send-to-device", {
      method: "POST",
      body: JSON.stringify({ id: selectedNc.id, code: selectedNc.code }),
      headers: { "Content-Type": "application/json" },
    });

    const res = await fetch(`/api/nc/${selectedNc.id}`);
    const updated = await res.json();

    setNcList((prev) =>
      prev.map((item) => (item.id === updated.id ? { ...item, status: updated.status } : item))
    );

    alert("장비로 전송되었습니다.");
  };

  

  return (
    <div>

      <NcStatusMonitor ncList={ncList} setNcList={setNcList} />

      <div className="font-semibold text-blue-700 mb-1">NC code</div>

      {/* 리스트 */}
      <div
        className={`space-y-1 pr-1 ${
          showScroll ? "max-h-[190px] overflow-y-auto" : "max-h-none overflow-y-hidden"
        }`}
      >
        {ncList.map((nc) => {
          const disabled = !isDeviceSelected;

          return (
            <div
              key={nc.id}
              className={`grid grid-cols-[36px_1.4fr_1.1fr_1.3fr_0.9fr] bg-white rounded-xl p-2 shadow border border-gray-100 items-center transition-opacity duration-200 ${
                disabled ? "opacity-50 pointer-events-none" : ""
              }`}
              style={{ minHeight: "36px" }}
            >
              {/* 체크박스 */}
              <input
                type="checkbox"
                checked={checkedId === nc.id}
                onChange={() => {
                  if (disabled) return;

                  const isSame = checkedId === nc.id;
                  const nextId = isSame ? null : nc.id;
                  setCheckedId(nextId);
                  onSelectNc(isSame ? "" : nc.code);
                }}
                className="w-4 h-4 accent-blue-500 mx-auto"
                disabled={disabled}
              />

              {/* Workplan */}
              <div>
                <div className="text-[11px] text-gray-400 leading-none">Workplan</div>
                <div className="font-bold text-xs truncate leading-tight">{nc.workplan}</div>
              </div>

              {/* NC code id */}
              <div>
                <div className="text-[11px] text-gray-400 leading-none">NC code id</div>
                <div className="font-mono text-blue-600 text-xs truncate leading-tight">
                  {nc.id}
                </div>
              </div>

              {/* File name */}
              <div>
                <div className="text-[11px] text-gray-400 leading-none">File name</div>
                <div className="text-xs truncate leading-tight">{nc.fileName}</div>
              </div>

              {/* Status */}
              <div>
                <div className="text-[11px] text-gray-400 leading-none">Status</div>
                {isDeviceSelected ? (
                  <div
                    className={
                      nc.status === "전송대기"
                        ? "text-orange-500 text-xs"
                        : "text-gray-700 text-xs"
                    }
                  >
                    {nc.status}
                  </div>
                ) : (
                  <div className="text-gray-300 text-xs italic">-</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 버튼 */}
      <div className="flex justify-end gap-2 mt-2">
        <ActionButton color="gray" onClick={handleSave} disabled={!selectedNc}>
          저장
        </ActionButton>
        <ActionButton color="blue" onClick={handleSend} disabled={isSendingDisabled||!selectedNc}>
          장비전송
        </ActionButton>
      </div>
    </div>
  );
}