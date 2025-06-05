//더미 데이터를 만들기 위한 데이터
export type NcStatus = "초기" | "전송대기" | "가공대기" | "가공완료";

export type NcData = {
  id: string;
  workplan: string;
  fileName: string;
  status: NcStatus;
  code: string;
};

// ✅ 메모리 저장소: 초기 상태
const ncStatusMap: Record<string, NcData> = {
  "NC-001": {
    id: "NC-001",
    workplan: "WP001",
    fileName: "sample1.nc",
    status: "초기",
    code: "%\nO001\nM30\n%",
  },
  "NC-002": {
    id: "NC-002",
    workplan: "WP002",
    fileName: "sample2.nc",
    status: "초기",
    code: "%\nO002\nM30\n%",
  },
  "NC-003": {
    id: "NC-003",
    workplan: "WP003",
    fileName: "sample3.nc",
    status: "초기",
    code: "%\nO003\nM30\n%",
  },
};

// ✅ 전체 리스트 반환
export function getAllNC(): NcData[] {
  return Object.values(ncStatusMap);
}

// ✅ 단일 NC 조회
export function getNCById(id: string): NcData | null {
  return ncStatusMap[id] ?? null;
}

// ✅ 상태 업데이트
export function updateStatus(id: string, newStatus: NcStatus): void {
  if (ncStatusMap[id]) {
    ncStatusMap[id].status = newStatus;
  }
}

// ✅ 가공대기 → 랜덤하게 가공완료로 전환 (30% 확률)
export function randomizeProcessingStatus(): void {
  Object.values(ncStatusMap).forEach((item) => {
    if (item.status === "가공대기" && Math.random() < 0.3) {
      item.status = "가공완료";
    }
  });
}