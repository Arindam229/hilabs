import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export async function GET() {
  const dataDir = process.env.PTD_DATA_DIR || path.join(process.cwd(), "..");
  const filePath = path.join(dataDir, "data/stage/c2/c2_summary.json");
  try {
    if (!fs.existsSync(filePath)) {
      return NextResponse.json({ error: "C2 summary not found" }, { status: 404 });
    }
    const content = fs.readFileSync(filePath, "utf-8");
    return NextResponse.json(JSON.parse(content));
  } catch (error) {
    console.error("Error reading C2 summary:", error);
    return NextResponse.json({ error: "Failed to read C2 summary" }, { status: 500 });
  }
}
