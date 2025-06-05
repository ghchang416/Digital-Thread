import { NextResponse } from "next/server";
import { getAllProducts } from "@/lib/productData";

export async function GET() {
  const products = getAllProducts();
  return NextResponse.json(products);
}