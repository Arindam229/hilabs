import { NextResponse } from "next/server";
import {
  getKPIData,
  getPipelineStages,
  getAddressStatusData,
  getFileQualityData,
} from "@/lib/api/data";

export async function GET() {
  try {
    const [kpiData, pipelineStages, addressStatus, fileQuality] = await Promise.all([
      getKPIData(),
      getPipelineStages(),
      getAddressStatusData(),
      getFileQualityData(),
    ]);

    return NextResponse.json({
      kpi: kpiData,
      pipeline: pipelineStages,
      addressStatus,
      fileQuality,
    });
  } catch (error) {
    console.error("Error fetching dashboard data:", error);
    return NextResponse.json(
      { error: "Failed to fetch dashboard data" },
      { status: 500 }
    );
  }
}