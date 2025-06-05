import { NextResponse } from "next/server";
import { getNCById, randomizeProcessingStatus } from "@/lib/ncDataStore";

export async function GET(_: Request, { params }: { params: { id: string } }) {
  randomizeProcessingStatus();
  const item = getNCById(params.id);
  if (!item) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json(item);
}