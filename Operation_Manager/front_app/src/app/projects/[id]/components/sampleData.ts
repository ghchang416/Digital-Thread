export const DEVICE_SAMPLE = [
  {
    id: "DEV-001",
    name: "머시닝센터 A",
    vendor: "Fanuc",
    activate: true,
  },
  {
    id: "DEV-002",
    name: "선반 B",
    vendor: "Siemens",
    activate: false,
  },
  {
    id: "DEV-003",
    name: "밀링 C",
    vendor: "Mitsubishi",
    activate: true,
  },
  {
    id: "DEV-004",
    name: "연삭기 D",
    vendor: "Heidenhain",
    activate: false,
  },
  {
    id: "DEV-005",
    name: "머시닝센터 E",
    vendor: "Fanuc",
    activate: true,
  },
  {
    id: "DEV-006",
    name: "머시닝센터 E",
    vendor: "Fanuc",
    activate: true,
  },
  {
    id: "DEV-007",
    name: "머시닝센터 E",
    vendor: "Fanuc",
    activate: true,
  },
  // ...더 추가 가능
];

export const NC_SAMPLE = [
  {
    id: "NC-001",
    workplan: "test_workplan1",
    fileName: "sample1.nc",
    status: "가공대기",
    code: `%\nO0050\nM98P51\nM30\n%`, // 실제 코드 내용
  },
  {
    id: "NC-002",
    workplan: "test_workplan2",
    fileName: "sample2.nc",
    status: "전송대기",
    code: `%\nO0020\nM30\n%`,
  },
  {
    id: "NC-003",
    workplan: "test_workplan3",
    fileName: "sample3.nc",
    status: "전송대기",
    code: `%\nO0020\nM30\n%`,
  },
  {
    id: "NC-004",
    workplan: "test_workplan4",
    fileName: "sample4.nc",
    status: "전송대기",
    code: `%\nO0020\nM30\n%`,
  },
  // 더 추가 가능
];

export const PRODUCT_SAMPLE = [
  {
    p_id: "P-001",
    uuid: "550e8400-e29b-41d4-a716-446655440000",
    startTime: "2024-06-04 오전 13:30",
    finishTime: "2024-06-04 오전 14:05",
  },
  {
    p_id: "P-002",
    uuid: "a6f6cf7c-60d5-4f9f-a45a-7097f5d0c22a",
    startTime: "2024-06-04 오후 14:10",
    finishTime: "2024-06-04 오후 15:02",
  },
  {
    p_id: "P-003",
    uuid: "f7f8d990-516c-4800-93d8-68b410e7e345",
    startTime: "2024-06-04 오전 15:10",
    finishTime: "2024-06-04 오전 15:55",
  },
  {
    p_id: "P-004",
    uuid: "f7f8d990-516c-4800-93d8-68b410e7e345",
    startTime: "2024-06-04 오전 15:10",
    finishTime: "2024-06-04 오전 15:55",
  },
  {
    p_id: "P-005",
    uuid: "f7f8d990-516c-4800-93d8-68b410e7e345",
    startTime: "2024-06-04 오전 15:10",
    finishTime: "2024-06-04 오전 15:55",
  },
];