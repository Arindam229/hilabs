import { NextResponse } from "next/server";
import { getAuditTrail } from "@/lib/api/data";

export async function GET() {
  try {
    const auditTrail = await getAuditTrail();
    return NextResponse.json(auditTrail);
  } catch (error) {
    console.error("Error fetching audit trail:", error);
    return NextResponse.json(
      { error: "Failed to fetch audit trail" },
      { status: 500 }
    );
  }
}