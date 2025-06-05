// app/api/nc/route.ts
import { NextResponse } from "next/server";
import { getAllNC, randomizeProcessingStatus } from "@/lib/ncDataStore";

export async function GET() {
  randomizeProcessingStatus(); // 가공대기 → 가공완료 랜덤 전이
  return NextResponse.json(getAllNC());
}