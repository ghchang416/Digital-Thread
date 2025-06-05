import { NextRequest, NextResponse } from "next/server";
import { updateStatus } from "@/lib/ncDataStore";

export async function POST(req: NextRequest) {
  const body = await req.json();
  updateStatus(body.id, "가공대기");
  return NextResponse.json({ success: true });
}