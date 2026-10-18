import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export const runtime = "nodejs";

const DATA_DIR = process.env.PTD_DATA_DIR || path.join(process.cwd(), "..");

const ALLOWED_FILES: Record<string, string> = {
  "final_provider_rates.xlsx": "data/out/final_provider_rates.xlsx",
  "c7_cost_effectiveness.xlsx": "data/out/c7_cost_effectiveness.xlsx",
  "c2_ppo_network.xlsx": "data/out/c2_ppo_network.xlsx",
  "c5result.csv": "data/stage/c5/c5result.csv",
  "c7_code_detail.csv": "data/stage/c7/c7_code_detail.csv",
};

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ file: string }> }
) {
  const { file } = await params;
  const relPath = ALLOWED_FILES[file];

  if (!relPath) {
    return new NextResponse("File not found or not permitted for download", { status: 404 });
  }

  const fullPath = path.isAbsolute(relPath) ? relPath : path.join(DATA_DIR, relPath);

  if (!fs.existsSync(fullPath)) {
    return new NextResponse("Requested deliverable file does not exist yet", { status: 404 });
  }

  const stat = fs.statSync(fullPath);
  const fileBuffer = fs.readFileSync(fullPath);

  const contentType = file.endsWith(".xlsx")
    ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    : file.endsWith(".csv")
    ? "text/csv"
    : "application/octet-stream";

  return new NextResponse(fileBuffer, {
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename="${file}"`,
      "Content-Length": stat.size.toString(),
    },
  });
}
