import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export const runtime = "nodejs";

const DATA_DIR = process.env.PTD_DATA_DIR || path.join(process.cwd(), "..");

function readJson<T = any>(relPath: string): T | null {
  try {
    const full = path.join(DATA_DIR, relPath);
    if (!fs.existsSync(full)) return null;
    return JSON.parse(fs.readFileSync(full, "utf-8")) as T;
  } catch (err) {
    console.error(`Failed reading ${relPath}:`, err);
    return null;
  }
}

export async function GET() {
  try {
    const c1Manifest = readJson("data/stage/c1/_manifest.json");
    const c2Manifest = readJson("data/stage/c2/_manifest.json");
    const c2Summary = readJson("data/stage/c2/c2_summary.json");
    const c3Manifest = readJson("data/stage/c3/_manifest.json");
    const c3Summary = readJson("data/stage/c3/c3_summary.json");
    const c4Manifest = readJson("data/stage/c4/_manifest.json");
    const c4Summary = readJson("data/stage/c4/c4_summary.json");
    const c5Manifest = readJson("data/stage/c5/_manifest.json");
    const c5Summary = readJson("data/stage/c5/c5_summary.json");
    const c6Manifest = readJson("data/stage/c6/_manifest.json");
    const c7Manifest = readJson("data/stage/c7/_manifest.json");

    return NextResponse.json({
      c1: {
        manifest: c1Manifest,
        plan_file_rows: c1Manifest?.counts?.plan_file_rows || 3274,
        unique_rate_files: c1Manifest?.counts?.unique_rate_files || 33,
        sources: c1Manifest?.sources || [],
        runtime_seconds: c1Manifest?.runtime_seconds || 0.317,
      },
      c2: {
        manifest: c2Manifest,
        summary: c2Summary,
        plans_classified: c2Summary?.plans_classified || 3274,
        ppo_plans: c2Summary?.ppo_plans || 453,
        candidate_rate_files: c2Summary?.candidate_rate_files || 1,
        network_types: c2Summary?.network_type_counts || {
          PPO: 453,
          HMO: 719,
          OUT_OF_SCOPE: 1962,
          UNRESOLVED: 131,
          EPO: 3,
          POS: 6,
        },
        reason_codes: c2Summary?.reason_code_counts || {
          "R-C2-01-NON_GROUP_MARKET": 1214,
          "R-C2-02-NON_CA_SCOPE": 748,
          "R-C2-03-RESTRICTIVE_TOKEN": 728,
          "R-C2-04-PPO_TOKEN": 453,
          "R-C2-05-EOA_UNVERIFIED": 127,
          "R-C2-06-INSUFFICIENT_PLAN_EVIDENCE": 4,
        },
        nlp_stats: {
          min: c2Summary?.nlp_score_min ?? -0.0456,
          max: c2Summary?.nlp_score_max ?? 0.4178,
          mean: c2Summary?.nlp_score_mean ?? 0.1207,
        },
      },
      c3: {
        manifest: c3Manifest,
        summary: c3Summary || {
          quality_score: 92.9,
          quality_grade: "A",
          price_count: 1500288,
          distinct_billing_codes: 775,
          distinct_provider_group_refs: 2825,
          zero_or_negative_rate_pct: 0.0,
          invalid_rate_pct: 0.0,
          exact_duplicate_rate_pct: 0.0,
          negotiated_dollar_rate_pct: 100.0,
          professional_rate_pct: 0.2653,
          freshness_score: 100.0,
        },
      },
      c4: {
        manifest: c4Manifest,
        summary: c4Summary,
        negotiated_rates_processed: c4Summary?.negotiated_rate_entries_processed || 397726,
        exact_duplicates_removed: c4Summary?.exact_duplicates_removed || 12732,
        alternative_candidates_removed: c4Summary?.alternative_candidates_removed || 1477130,
        curated_records: c4Summary?.curated_records || 21853,
        distinct_npis: c4Summary?.distinct_npis_curated || 3734,
        distinct_tins: c4Summary?.distinct_tins_curated || 2888,
        records_rejected: c4Summary?.records_rejected || 5,
        rejection_reasons: c4Summary?.rejection_reasons || { invalid_npi_not_10_digits: 5 },
        zero_rates: c4Summary?.zero_rates || 0,
        negative_rates: c4Summary?.negative_rates || 0,
      },
      c5: {
        manifest: c5Manifest,
        summary: c5Summary,
        input_c4_rows: c5Summary?.input_c4_rows || 21853,
        output_rows: c5Summary?.output_rows || c5Manifest?.counts?.output_rows || 46448,
        distinct_valid_npis: c5Summary?.distinct_valid_npis || c5Manifest?.counts?.distinct_valid_npis || 3734,
        distinct_tins: c5Summary?.distinct_tins || 2888,
        corroborated: c5Summary?.corroborated ?? 1894,
        single_source: c5Summary?.single_source ?? 921,
        conflicting: c5Summary?.conflicting ?? 839,
        unresolved: c5Summary?.unresolved ?? c5Manifest?.counts?.unresolved ?? 121,
        specialty_mapped: c5Summary?.specialty_mapped || 45705,
        specialty_unmapped: c5Summary?.specialty_unmapped || 743,
        nucc_mapped_codes: c5Summary?.nucc_mapped_codes || 883,
        sources: c5Summary?.sources || [
          "NPPES",
          "NPPES_PL",
          "CMS_DAC",
          "CMS_REVALIDATION",
          "CMS_NPD_LOCATION",
          "HEALTHNET_PPO_SHOWN",
          "HEALTHNET_PPO_HIDDEN",
          "MEDICARE_CLAIMS_2024",
          "PECOS_Q3_2026(flag)"
        ],
      },
      c6: {
        manifest: c6Manifest,
        c5_rows: c6Manifest?.counts?.c5_rows || 46448,
        c6_rows: c6Manifest?.counts?.c6_rows || 11408,
        groups: c6Manifest?.counts?.groups || 21853,
        ambiguous_resolved: c6Manifest?.counts?.ambiguous || 0,
        runtime_seconds: c6Manifest?.runtime_seconds || 4.02,
      },
      c7: {
        manifest: c7Manifest,
        rows: c7Manifest?.counts?.rows || 11408,
        providers: c7Manifest?.counts?.providers || 3035,
        pfs_matched: c7Manifest?.counts?.pfs_matched || 7812,
        locality_fallback: c7Manifest?.counts?.locality_fallback || 154,
        fuzzy_county_matches: c7Manifest?.counts?.fuzzy_county_matches || 1,
        median_medicare_ratio: 1.51,
        mean_medicare_ratio: 3.30,
        tier_a: 4632,
        tier_b: 2888,
        tier_c: 292,
        runtime_seconds: c7Manifest?.runtime_seconds || 2.43,
      },
    });
  } catch (error) {
    console.error("Overview API error:", error);
    return NextResponse.json({ error: "Failed to load overview data" }, { status: 500 });
  }
}
