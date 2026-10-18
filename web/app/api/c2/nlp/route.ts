import { NextResponse } from "next/server";
import { execSync } from "child_process";
import path from "path";

export async function GET() {
  const dataDir = process.env.PTD_DATA_DIR || path.join(process.cwd(), "..");
  const parquet = path.join(dataDir, "data/stage/c2/plan_network.parquet");
  const script = path.join(dataDir, "scripts/export_c2_nlp.py");
  try {
    const out = execSync(`python3 "${script}" "${parquet}"`, { encoding: "utf-8", timeout: 60000 });
    return NextResponse.json(JSON.parse(out));
  } catch (error) {
    console.error("C2 NLP export failed:", error);
    return NextResponse.json({ error: "Failed to export C2 NLP data" }, { status: 500 });
  }
}
