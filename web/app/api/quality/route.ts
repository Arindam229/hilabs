import { NextResponse } from "next/server";
import { getFileQualityData } from "@/lib/api/data";

export async function GET() {
  try {
    const fileQuality = await getFileQualityData();
    return NextResponse.json(fileQuality);
  } catch (error) {
    console.error("Error fetching file quality data:", error);
    return NextResponse.json(
      { error: "Failed to fetch file quality data" },
      { status: 500 }
    );
  }
}