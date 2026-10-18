import fs from "fs";
import path from "path";
import {
  C4Summary,
  C5Summary,
  Manifest,
  KPIData,
  PipelineStage,
  AddressStatusData,
  FileQualityData,
  RateRecord,
  AuditEntry,
} from "@/lib/types";

// Get the data directory from environment or default
const DATA_DIR = process.env.PTD_DATA_DIR || path.join(process.cwd(), "../../data");

function readJsonFile<T>(filePath: string): T | null {
  try {
    const fullPath = path.isAbsolute(filePath) ? filePath : path.join(DATA_DIR, filePath);
    if (!fs.existsSync(fullPath)) {
      console.warn(`File not found: ${fullPath}`);
      return null;
    }
    const content = fs.readFileSync(fullPath, "utf-8");
    return JSON.parse(content) as T;
  } catch (error) {
    console.error(`Error reading ${filePath}:`, error);
    return null;
  }
}

function readManifest(stage: string): Manifest | null {
  return readJsonFile<Manifest>(`data/stage/${stage}/_manifest.json`);
}

export async function getC4Summary(): Promise<C4Summary | null> {
  return readJsonFile<C4Summary>("data/stage/c4/c4_summary.json");
}

export async function getC5Summary(): Promise<C5Summary | null> {
  return readJsonFile<C5Summary>("data/stage/c5/c5_summary.json");
}

export async function getManifest(stage: string): Promise<Manifest | null> {
  return readManifest(stage);
}

export async function getAllManifests(): Promise<Manifest[]> {
  const stages = ["c1", "c2", "c3", "c4", "c5", "c6"];
  const manifests = await Promise.all(stages.map((s) => getManifest(s)));
  return manifests.filter((m): m is Manifest => m !== null);
}

export async function getKPIData(): Promise<KPIData> {
  const [c4, c5] = await Promise.all([getC4Summary(), getC5Summary()]);

  const ratesExtracted = c4?.output_records_generated || 0;
  const npis = c4?.distinct_npis_curated || c4?.distinct_npis || 0;
  const tins = c4?.distinct_tins_curated || c4?.distinct_tins || 0;
  const verifiedAddressesPct = c5 && c5.output_rows > 0
    ? Math.round(((c5.corroborated + c5.single_source) / c5.output_rows) * 100)
    : 0;
  const fileGrade = getFileGrade(c4?.c3_quality_score || 0);

  return {
    ratesExtracted,
    npis,
    tins,
    verifiedAddressesPct,
    fileGrade,
  };
}

function getFileGrade(score: number): string {
  if (score >= 90) return "A";
  if (score >= 80) return "B";
  if (score >= 70) return "C";
  if (score >= 60) return "D";
  return "F";
}

export async function getPipelineStages(): Promise<PipelineStage[]> {
  const manifests = await getAllManifests();
  const c4 = await getC4Summary();
  const c5 = await getC5Summary();

  const stageLabels: Record<string, string> = {
    c1: "Index Parse",
    c2: "PPO Classification",
    c3: "File Quality",
    c4: "Rate Selection",
    c5: "Address Linking",
    c6: "Provider Rates",
  };

  return manifests.map((m) => ({
    stage: m.stage,
    label: stageLabels[m.stage] || m.stage.toUpperCase(),
    status: "completed" as const,
    runtime_seconds: m.runtime_seconds,
    records_in: getRecordsIn(m),
    records_out: getRecordsOut(m),
  }));
}

function getRecordsIn(m: Manifest): number {
  const counts = m.counts;
  return (
    counts.plan_file_rows ||
    counts.plans_classified ||
    counts.price_rows_scored ||
    counts.negotiated_rate_entries_processed ||
    counts.input_c4_rows ||
    counts.c5_rows ||
    0
  );
}

function getRecordsOut(m: Manifest): number {
  const counts = m.counts;
  return (
    counts.unique_rate_files ||
    counts.ppo_plans ||
    counts.curated_records ||
    counts.output_records_generated ||
    counts.output_rows ||
    counts.c6_rows ||
    0
  );
}

export async function getAddressStatusData(): Promise<AddressStatusData> {
  const c5 = await getC5Summary();
  if (!c5) {
    return { corroborated: 0, single_source: 0, conflicting: 0, unresolved: 0, total: 0 };
  }
  const total = c5.corroborated + c5.single_source + c5.conflicting + c5.unresolved;
  return {
    corroborated: c5.corroborated,
    single_source: c5.single_source,
    conflicting: c5.conflicting,
    unresolved: c5.unresolved,
    total,
  };
}

export async function getFileQualityData(): Promise<FileQualityData> {
  const c4 = await getC4Summary();
  const c3Manifest = await getManifest("c3");

  const score = c4?.c3_quality_score || 0;
  const grade = getFileGrade(score);

  return {
    grade,
    score,
    metrics: [
      { name: "C3 Quality Score", value: `${score}%`, status: score >= 70 ? "pass" : "warn" },
      { name: "Exact Duplicates", value: c4?.exact_duplicates || 0, status: "warn" },
      { name: "Alternative Candidates Removed", value: c4?.alternative_candidates_removed || 0, status: "pass" },
      { name: "Records Rejected", value: c4?.records_rejected || 0, status: "fail" },
      { name: "Negative Rates", value: c4?.negative_rates || 0, status: "pass" },
      { name: "Zero Rates", value: c4?.zero_rates || 0, status: "pass" },
      { name: "Invalid Non-numeric Rates", value: c4?.missing_invalid_nonnumeric_rates || 0, status: "pass" },
    ],
    outliers: [
      { type: "Exact Duplicates", count: c4?.exact_duplicates || 0, severity: "medium" },
      { type: "Alternative Candidates", count: c4?.alternative_candidates_removed || 0, severity: "low" },
      { type: "Rejected Records", count: c4?.records_rejected || 0, severity: "high" },
    ],
  };
}

export async function getRateRecords(
  search?: string,
  filters?: {
    billing_code?: string;
    specialty?: string;
    address_status?: string;
    billing_class?: string;
  },
  page = 1,
  pageSize = 50
): Promise<{ records: RateRecord[]; total: number }> {
  // In a real implementation, this would query the final_provider_rates.xlsx or CSV
  // For now, return mock data structure
  const c4 = await getC4Summary();
  const c5 = await getC5Summary();

  const total = c4?.curated_records || 0;

  // Return sample/mock data for now - in production this would query the actual data
  const mockRecords: RateRecord[] = Array.from({ length: Math.min(pageSize, total) }, (_, i) => ({
    npi: `12345678${String(i).padStart(2, "0")}`,
    tin: `12-${String(1000000 + i).padStart(7, "0")}`,
    address: `${100 + i} Main St, Suite ${100 + i}, City, CA 90210`,
    billing_code: ["99213", "99214", "99215", "99203", "99204"][i % 5],
    specialty: ["Internal Medicine", "Family Practice", "Cardiology", "Dermatology", "Orthopedics"][i % 5],
    rate: Math.round(100 + Math.random() * 400),
    address_status: ["corroborated", "single_source", "conflicting", "unresolved"][i % 4],
    specialty_source: ["NPPES", "NPPES_PL", "CMS_DAC"][i % 3],
    selection_rule: "R-C4-01: Highest negotiated rate",
    candidate_count: 3 + (i % 4),
  }));

  return { records: mockRecords, total };
}

export async function getAuditTrail(): Promise<AuditEntry[]> {
  const manifests = await getAllManifests();

  return manifests.map((m) => ({
    stage: m.stage,
    timestamp: new Date((m.sources?.[0]?.last_modified ?? 0) * 1000 || Date.now()).toISOString(),
    git_sha: m.git_sha.slice(0, 8),
    runtime_seconds: m.runtime_seconds,
    counts: m.counts,
  }));
}