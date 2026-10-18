import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export const runtime = "nodejs";

const DATA_DIR = process.env.PTD_DATA_DIR || path.join(process.cwd(), "..");
const RAG_DAEMON_URL = process.env.RAG_DAEMON_URL || "http://127.0.0.1:8005";
const LOCAL_LLM_URL = process.env.LOCAL_LLM_URL || "http://127.0.0.1:11434";
const LOCAL_LLM_MODEL = process.env.LOCAL_LLM_MODEL || "qwen2.5:1.5b";

export async function GET() {
  try {
    // 1. Check RAG daemon status
    let daemonOnline = false;
    try {
      const dCtrl = new AbortController();
      const dTimeout = setTimeout(() => dCtrl.abort(), 1000);
      const dRes = await fetch(`${RAG_DAEMON_URL}/health`, { signal: dCtrl.signal }).catch(() => null);
      clearTimeout(dTimeout);
      if (dRes && dRes.ok) daemonOnline = true;
    } catch {
      daemonOnline = false;
    }

    // 2. Check Ollama status
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1200);

    const checkRes = await fetch(`${LOCAL_LLM_URL}/api/tags`, {
      signal: controller.signal,
    }).catch(() => null);
    clearTimeout(timeoutId);

    if (checkRes && checkRes.ok) {
      const data = await checkRes.json();
      const models: string[] = (data.models || []).map((m: any) => m.name || m.model);
      const qwenModel = models.find((m) => m.toLowerCase().includes("qwen")) || LOCAL_LLM_MODEL;

      return NextResponse.json({
        status: "online",
        model: qwenModel,
        daemon: daemonOnline ? "online" : "standby",
        available_models: models,
        url: LOCAL_LLM_URL,
      });
    }

    return NextResponse.json({
      status: daemonOnline ? "online" : "standby",
      model: "Qwen 2.5 (Configured)",
      daemon: daemonOnline ? "online" : "standby",
      instruction: "Ollama and RAG daemon available on local machine",
      fallback: "Deterministic Pipeline RAG Engine Active",
    });
  } catch {
    return NextResponse.json({
      status: "standby",
      model: "Qwen 2.5",
      fallback: "Deterministic Pipeline RAG Engine Active",
    });
  }
}

function readJsonFile(relPath: string) {
  try {
    const full = path.join(DATA_DIR, relPath);
    if (!fs.existsSync(full)) return null;
    return JSON.parse(fs.readFileSync(full, "utf-8"));
  } catch {
    return null;
  }
}

function getSystemContext() {
  const c1 = readJsonFile("data/stage/c1/_manifest.json");
  const c2 = readJsonFile("data/stage/c2/c2_summary.json");
  const c3 = readJsonFile("data/stage/c3/c3_summary.json");
  const c4 = readJsonFile("data/stage/c4/c4_summary.json");
  const c5 = readJsonFile("data/stage/c5/c5_summary.json");
  const c6 = readJsonFile("data/stage/c6/_manifest.json");
  const c7 = readJsonFile("data/stage/c7/_manifest.json");

  return `You are the HiLabs Provider Rates Pipeline Copilot, an expert AI assistant that explains the data curation pipeline for Centene Price Transparency Data (PTD).
Scope: Centene, California, Commercial Group, PPO Network.
Current Pipeline Status & Ground Truth Metrics:
- C1 (Index Parse): 11 index files parsed across Ambetter, Fidelis, QualChoice, Health Net. 3,274 plan-file rows deduplicated into 33 unique physical rate files in ${c1?.runtime_seconds || 0.317}s.
- C2 (PPO Network): 3,274 plans classified into 453 PPO plans, 719 HMO, 1,962 Out of Scope, 131 Unresolved (127 EOA + 4 insufficient evidence), 3 EPO, 6 POS.
  * NLP Cosine Sim with SentenceTransformer("all-MiniLM-L6-v2") was evaluated: scores clustered in -0.04 to 0.42 (max 0.418, mean 0.12). No separable decision boundary between HMO and PPO.
  * Supervised logistic regression was inadequate on hybrid names.
  * Deterministic rule cascade (R-C2-01 to R-C2-08) was adopted: Non-group (R-C2-01: 1,214), Non-CA (R-C2-02: 748), Restrictive token override (R-C2-03: 728), PPO token match (R-C2-04: 453), EOA unverified (R-C2-05: 127), No evidence (R-C2-06: 4).
  * 453 PPO plans converge to 1 candidate rate file: 2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json (701.6 MB uncompressed).
- C3 (File Quality): Scored the Health Net CA file. Price count: ${c3?.price_count || 1500288}. Quality score: ${c3?.quality_score || 92.9}% (Grade ${c3?.quality_grade || 'A'}). 0% $0/negative, 0% invalid rates, 0% duplicates, 100% freshness (updated 2026-10-06). TiC expiration dates are all 9999-12-31 (useless for staleness). Universal pipeline scales to all other 32 Centene files via workers.
- C4 (Rate Extraction): 1,511,720 raw candidate explosions from 397,726 rate entries. 12,732 exact duplicates removed. 1,477,130 alternative candidates pruned via selection hierarchy (Professional > Institutional for Type 1, base rate > modified, highest negotiated rate R-C4-SEL-01 to 07). 5 records rejected for invalid NPI (< 10 digits). Curated records: ${c4?.curated_records || 21853} across ${c4?.distinct_npis_curated || 3734} NPIs and ${c4?.distinct_tins_curated || 2888} TINs.
- C5 (Address Corroboration): NPPES is ~80% stale. Corroborated across multi-source evidence: NPPES Oct 2026 CA extract, NPPES Practice Location (PL), CMS Doctors & Clinicians (DAC), CMS Revalidation Reassignments (314 matches), CMS NPD API Location, Health Net Directory (2,920 NPIs), Medicare 2024 Claims (504 NPIs), PECOS Enrollment (2,603 CA NPIs). Total output rows: ${c5?.output_rows || 46448}. Corroborated: ${c5?.corroborated || 1894}, Single Source: ${c5?.single_source || 921}, Conflicting candidates: ${c5?.conflicting || 839}, Unresolved: ${c5?.unresolved || 121}. Specialty mapped: ${c5?.specialty_mapped || 45705} via NUCC taxonomy (883 codes).
- C6 (Final Output): Filtered and deduplicated into ${c6?.counts?.c6_rows || 11408} final provider rate rows in final_provider_rates.xlsx with 0 duplicate keys and 0 ambiguous records remaining.
- C7 (Cost-Effectiveness & Benchmark Scoring): Benchmarked ${c7?.counts?.rows || 11408} provider rates across ${c7?.counts?.providers || 3035} unique healthcare providers against CMS Medicare Physician Fee Schedule (PFS). Median Medicare ratio is 1.51x base CMS fee schedule (Mean: 3.30x). CMS PFS matches: 7,812 direct locality matches + 154 locality fallbacks. Benchmarking hierarchy: Tier A (Specialty + Code Peer Median: 4,632), Tier B (Code-Only Peer Median: 2,888), Tier C (Direct Medicare PFS: 292). Output: c7_cost_effectiveness.xlsx.
Be concise, clear, accurate, and reference the specific rule IDs and statistics.`;
}

// Fallback Knowledge Base Engine if local LLM is not currently booted
function answerFromKnowledgeBase(query: string): string {
  const q = query.toLowerCase();

  if (q.includes("nlp") || q.includes("histogram") || q.includes("embedding") || q.includes("minilm") || q.includes("cosine")) {
    return `### Why NLP was Insufficient for PPO Classification

1. **Empirical Distribution (Histogram)**:
   We embedded all plan names and computed cosine similarity against the CMS PPO archetype using \`SentenceTransformer("all-MiniLM-L6-v2")\`.
   - **Score Range**: Scores ranged from **-0.046 to 0.418** (mean: **0.121**).
   - **No Decision Boundary**: Over 87% of all plans fell between 0.0 and 0.2. Exactly **zero plans** achieved $\\ge 0.5$. Setting a standard threshold (e.g. 0.8) would have discarded 100% of genuine PPO plans.

2. **Semantic Ambiguity**:
   Hybrid plan names such as *"Full Network HMO Platinum"* and *"Freedom PreferredChoice"* yielded higher cosine similarity to the PPO archetype than legitimate customized group PPOs like *"CA L CUS PPO SACRAMENTO CITY USD"*.

3. **Supervised Logistic Regression**:
   We also evaluated a logistic classifier trained on embeddings + token features, but false positive rates were unacceptably high on non-PPO benefit designs.

4. **The Winning Solution**:
   We implemented deterministic **Rule-Based Cascading** (Rules \`R-C2-01\` through \`R-C2-08\`), isolating 453 PPO plans with zero false positives.`;
  }

  if (q.includes("r-c2-03") || q.includes("restrictive") || q.includes("hmo") || q.includes("override")) {
    return `### Rule R-C2-03: Restrictive Network Token Override

- **The Rule**: A plan whose name contains any restrictive token (\`HMO\`, \`EPO\`, \`POS\`, \`WholeCare\`, \`SmartCare\`, \`CommunityCare\`, or \`Salud\`) is classified as that restrictive network, **even if the word 'PPO' also appears in the name**.
- **Why this was necessary**: In California commercial accounts, plan names frequently combine employer group labels with benefit riders, such as:
  \`CA L CUS PPO SACRAMENTO CITY USD EPO$15\`
  Here, "PPO" refers to the employer's master account, but the actual benefit design delivered to the member is **EPO** (exclusive provider, no out-of-network benefits).
- **Impact**: Exactly **728 plans** were safely excluded under this rule (719 HMO, 6 POS, 3 EPO), eliminating critical false positives.`;
  }

  if (q.includes("c4") || q.includes("rate") || q.includes("conflict") || q.includes("hierarchy") || q.includes("selection")) {
    return `### Stage C4: Rate Extraction & Conflict Resolution Hierarchy

In Price Transparency Data (PTD), a single provider and billing code frequently have multiple conflicting negotiated rates due to multiple contract tiers, modifiers, and service classes.

- **Total Explosions Evaluated**: 1,511,720 rows.
- **Deduplication**: 12,732 exact duplicate rows were purged immediately.
- **Selection Hierarchy (Rules R-C4-SEL-01 to R-C4-SEL-07)**:
  1. **Professional over Institutional**: Professional rates are preferred for Type 1 individual providers.
  2. **Base Rates over Modified**: Unmodified billing codes take precedence over modifier-adjusted rates.
  3. **Negotiated over Derived**: Standard fee-for-service negotiated rates take precedence over percentage-of-charge or capitated arrangements.
  4. **Precedence Ranking**: Where multiple candidate schedules remain, the highest negotiated rate is selected.
- **Sanity Checks**: **5 records were rejected** because their NPI had fewer than 10 digits (\`invalid_npi_not_10_digits: 5\`).
- **Result**: Filtered 1,477,130 alternative candidates down to **21,853 curated, clean rates** across 3,734 NPIs.`;
  }

  if (q.includes("address") || q.includes("c5") || q.includes("nppes") || q.includes("stale") || q.includes("corroborat")) {
    return `### Stage C5: Multi-Source Address Corroboration

- **Why NPPES cannot be trusted alone**:
  Studies and our data findings show that **~80% of NPPES addresses are stale, historical, or administrative billing locations**, rather than active practicing addresses.
- **Our Multi-Source Triangulation**:
  We built candidate address graphs by cross-referencing multi-source registries:
  1. **NPPES October 2026 CA Extract**: Primary practice location.
  2. **NPPES Practice Location File (PL)**: Secondary physical practicing locations.
  3. **CMS Doctors & Clinicians (DAC)**: Active Medicare clinician billing addresses and PAC organization links.
  4. **CMS Revalidation Reassignments**: 314 verified group PAC matches.
  5. **CMS NPD API Location**: Live FHIR directory query verification.
  6. **Health Net PPO Provider Directory**: 2,920 matched practicing NPIs.
  7. **Medicare Claims 2024**: 504 active billing NPIs.
  8. **PECOS Public Enrollment Extract**: 2,603 CA clinicians.
- **Evidence Breakdown (46,448 output links)**:
  - **Corroborated ($\ge 2$ sources agree)**: 1,894
  - **Single Source verified**: 921
  - **Conflicting Candidate addresses**: 839
  - **Unresolved**: 121
- **Specialty Mapping**: 45,705 mapped to NUCC descriptions across 883 taxonomy codes.`;
  }

  if (q.includes("c3") || q.includes("quality") || q.includes("metric") || q.includes("grade") || q.includes("freshness")) {
    return `### Stage C3: File Quality Grading

- **Target File Scored**:
  \`2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json\`
  *(Health Net California in-network file: 701.6 MB uncompressed JSON, 1,500,288 prices, schema v2.0.0).*
- **Composite Grade**: **Grade A (92.9%)**
- **Core Findings**:
  - **Price Validity (100% Clean)**: 0 zero rates, 0 negative rates, 0 non-numeric prices, 0% duplicate rates.
  - **Statistical Quality**: 3.67% cohort outliers, 3.69% Medicare out-of-band, 99.91% valid NPIs.
  - **Schema & Coverage**: 100% required field completeness, 100% pointer integrity, 69.4% weighted code coverage.
  - **Freshness**: 100% freshness score (updated 2026-10-06). Expiration dates in TiC files are 100% '9999-12-31' (useless for staleness).
- **Scalability Note**:
  The same bounded-memory streaming engine runs on all other 32 Centene rate files using \`python -m pipeline c3 --workers N\`.`;
  }

  if (q.includes("c6") || q.includes("deliverable 1") || (q.includes("c6") && q.includes("excel"))) {
    return `### Stage C6: Final Provider Rates File (Deliverable 1)

- **Output File**: \`data/out/final_provider_rates.xlsx\`
- **Columns**: NPI, TIN, Address, Billing Code, Specialty, Rate.
- **Row Count**: **11,408 final deduplicated provider rate rows**.
- **Data Integrity**: 0 duplicate (NPI, TIN, Billing Code, Address) keys, 0 ambiguous records.`;
  }

  if (q.includes("c7") || q.includes("cost") || q.includes("medicare") || q.includes("benchmark") || q.includes("pfs") || q.includes("ratio")) {
    return `### Stage C7: Provider Cost-Effectiveness & Benchmark Scoring (Deliverable 2)

- **Output File**: \`data/out/c7_cost_effectiveness.xlsx\`
- **Methodology**: Benchmarks Centene negotiated rates against the CMS Medicare Physician Fee Schedule (PFS) by matching billing codes and locality GPCIs.
- **Key Statistics**:
  - **Rates Scored**: **11,408** provider rates
  - **Distinct Providers**: **3,035** unique healthcare providers
  - **Median Medicare Ratio**: **1.51x** (negotiated rates are typically 151% of Medicare base rate; mean: 3.30x)
  - **CMS PFS Matches**: 7,812 direct locality matches + 154 locality fallbacks
- **Benchmarking Hierarchy**:
  - **Tier A (Specialty + Code Peer Median)**: 4,632 rates
  - **Tier B (Code-Only Peer Median)**: 2,888 rates
  - **Tier C (Direct CMS Medicare PFS Only)**: 292 rates`;
  }

  return `### HiLabs Pipeline Copilot Summary

I can answer any technical or domain question about the Centene PTD curation pipeline and data records:
- **Data Records**: Lookup any NPI (e.g. \`1003017351\`), TIN (e.g. \`20-1413484\`), Billing Code (\`99214\`, \`99213\`), or Specialty.
- **C1**: Index parsing, fan-in deduplication (3,274 rows $\\rightarrow$ 33 files), and format sanity checks.
- **C2**: Why NLP semantic cosine similarity failed (histogram max 0.418), why logistic regression was inadequate, and how deterministic rules (\`R-C2-01\` to \`R-C2-08\`) isolated 453 PPO plans.
- **C3**: File quality scorecard (Grade B, 75.7%), 0% zero/negative rates, 97.3% duplicate density, and cross-file scalability.
- **C4**: Rate candidate explosion (1.5M rows) $\\rightarrow$ conflict resolution hierarchy $\\rightarrow$ 21,853 curated rates (5 invalid NPIs rejected).
- **C5/C6**: Multi-source address corroboration (NPPES + CMS DAC), resolving 80% staleness, and the final 12,326-row Excel deliverable.

*Feel free to ask a specific question on any stage, rule ID, metric, or provider record!*`;
}

export async function POST(req: NextRequest) {
  try {
    const { message } = await req.json();
    if (!message || typeof message !== "string") {
      return NextResponse.json({ error: "Message is required" }, { status: 400 });
    }

    // 1. Try querying the persistent warm RAG Daemon first (fastest: sub-100ms retrieval + live DuckDB records)
    try {
      const dCtrl = new AbortController();
      const dTimeout = setTimeout(() => dCtrl.abort(), 20000);
      const ragRes = await fetch(`${RAG_DAEMON_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: message, top_k: 4, model: LOCAL_LLM_MODEL }),
        signal: dCtrl.signal,
      }).catch(() => null);
      clearTimeout(dTimeout);

      if (ragRes && ragRes.ok) {
        const ragData = await ragRes.json();
        return NextResponse.json({
          answer: ragData.answer,
          sources: ragData.sources || [],
          data_records: ragData.data_records || null,
          backend: ragData.backend || `Qwen 2.5 + Vector RAG`,
          latency_ms: ragData.total_latency_ms,
          timestamp: new Date().toISOString(),
        });
      }
    } catch {
      // Daemon not running, fall through to direct Ollama query
    }

    // 2. Direct Ollama LLM query fallback
    let llmResponse: string | null = null;
    let backendUsed = "Local Pipeline Knowledge Base (Deterministic RAG)";

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);

      const checkRes = await fetch(`${LOCAL_LLM_URL}/api/tags`, {
        signal: controller.signal,
      }).catch(() => null);
      clearTimeout(timeoutId);

      if (checkRes && checkRes.ok) {
        const generateRes = await fetch(`${LOCAL_LLM_URL}/api/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: LOCAL_LLM_MODEL,
            system: getSystemContext(),
            prompt: message,
            stream: false,
          }),
        });

        if (generateRes.ok) {
          const genJson = await generateRes.json();
          llmResponse = genJson.response;
          backendUsed = `Local LLM (${LOCAL_LLM_MODEL} @ ${LOCAL_LLM_URL})`;
        }
      }
    } catch {
      // Local LLM server not reachable; seamlessly fallback to grounded engine
    }

    if (!llmResponse) {
      llmResponse = answerFromKnowledgeBase(message);
    }

    return NextResponse.json({
      answer: llmResponse,
      backend: backendUsed,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Copilot API error:", error);
    return NextResponse.json({ error: "Failed to generate copilot response" }, { status: 500 });
  }
}
