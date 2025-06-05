import { NextResponse } from "next/server";


const DEVICE_SAMPLE = [
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

export async function GET(request: Request) {
    return NextResponse.json({
    devices: DEVICE_SAMPLE,
    totalCount: DEVICE_SAMPLE.length,
  });
}