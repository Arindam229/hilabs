import { NextResponse } from "next/server";
import { getRateFilterOptions } from "@/lib/api/data";

export async function GET() {
  try {
    const options = await getRateFilterOptions();
    return NextResponse.json(options);
  } catch (error) {
    console.error("Error fetching rate options:", error);
    return NextResponse.json(
      { billingCodes: [], specialties: [], addressStatuses: [] },
      { status: 500 }
    );
  }
}
