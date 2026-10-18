import { NextResponse } from "next/server";
import { getAddressStatusData } from "@/lib/api/data";

export async function GET() {
  try {
    const addressStatus = await getAddressStatusData();
    return NextResponse.json(addressStatus);
  } catch (error) {
    console.error("Error fetching address status data:", error);
    return NextResponse.json(
      { error: "Failed to fetch address status data" },
      { status: 500 }
    );
  }
}