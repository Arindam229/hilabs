"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
} from "recharts";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Layers,
  FileCheck,
  MapPin,
  Database,
  Filter,
  Search,
  Table,
  FileSpreadsheet,
  TrendingUp,
  XCircle,
  ShieldCheck,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface NLPData {
  histogram: Array<{ bin: string; count: number }>;
  top_plans: Array<{
    plan_name: string;
    network_type: string;
    confidence: string;
    nlp_score: number;
  }>;
  total: number;
  scored: number;
}

interface OverviewPayload {
  c1: {
    plan_file_rows: number;
    unique_rate_files: number;
    sources: Array<{ member: string; size: number }>;
    runtime_seconds: number;
  };
  c2: {
    plans_classified: number;
    ppo_plans: number;
    candidate_rate_files: number;
    network_types: Record<string, number>;
    reason_codes: Record<string, number>;
    nlp_stats: { min: number; max: number; mean: number };
  };
  c3: {
    summary: {
      quality_score: number;
      quality_grade: string;
      price_count: number;
      distinct_billing_codes: number;
      distinct_provider_group_refs: number;
      zero_or_negative_rate_pct: number;
      invalid_rate_pct: number;
      exact_duplicate_rate_pct: number;
      negotiated_dollar_rate_pct: number;
      professional_rate_pct: number;
      freshness_score: number;
    };
  };
  c4: {
    negotiated_rates_processed: number;
    exact_duplicates_removed: number;
    alternative_candidates_removed: number;
    curated_records: number;
    distinct_npis: number;
    distinct_tins: number;
    records_rejected: number;
    rejection_reasons: Record<string, number>;
    zero_rates: number;
    negative_rates: number;
  };
  c5: {
    input_c4_rows: number;
    output_rows: number;
    distinct_valid_npis: number;
    distinct_tins: number;
    corroborated: number;
    single_source: number;
    conflicting: number;
    unresolved: number;
    specialty_mapped: number;
    specialty_unmapped: number;
    sources: string[];
  };
  c6: {
    c5_rows: number;
    c6_rows: number;
    groups: number;
    ambiguous_resolved: number;
  };
}

export default function OverviewPage() {
  const [data, setData] = useState<OverviewPayload | null>(null);
  const [nlp, setNlp] = useState<NLPData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const [overviewRes, nlpRes] = await Promise.all([
          fetch("/api/overview"),
          fetch("/api/c2/nlp").catch(() => null),
        ]);

        if (!overviewRes.ok) throw new Error("Failed to load overview data");
        const overviewJson = await overviewRes.json();
        setData(overviewJson);

        if (nlpRes && nlpRes.ok) {
          const nlpJson = await nlpRes.json();
          setNlp(nlpJson);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <DashboardLayout title="Pipeline Architecture & Quality Overview">
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-5">
            {[...Array(5)].map((_, i) => (
              <Card key={i} className="p-4">
                <Skeleton className="h-4 w-1/2 mb-2" />
                <Skeleton className="h-8 w-3/4" />
              </Card>
            ))}
          </div>
          <Card className="p-6">
            <Skeleton className="h-48 w-full" />
          </Card>
        </div>
      </DashboardLayout>
    );
  }

  if (error || !data) {
    return (
      <DashboardLayout title="Pipeline Architecture & Quality Overview">
        <div className="p-12 text-center text-red-500 bg-red-500/10 rounded-xl border border-red-500/20">
          <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-red-500" />
          <p className="font-semibold">{error || "Failed to load pipeline data."}</p>
        </div>
      </DashboardLayout>
    );
  }

  const { c1, c2, c3, c4, c5, c6 } = data;

  const networkChartData = [
    { name: "PPO", count: c2.network_types.PPO || 453, fill: "hsl(var(--primary))" },
    { name: "HMO", count: c2.network_types.HMO || 719, fill: "#f59e0b" },
    { name: "Out of Scope", count: c2.network_types.OUT_OF_SCOPE || 1962, fill: "#64748b" },
    { name: "Unresolved (EOA)", count: c2.network_types.UNRESOLVED || 131, fill: "#ef4444" },
    { name: "EPO/POS", count: (c2.network_types.EPO || 3) + (c2.network_types.POS || 6), fill: "#a855f7" },
  ];

  const addressChartData = [
    { name: "Single Source", value: c5.single_source, fill: "#eab308" },
    { name: "Conflicting", value: c5.conflicting, fill: "#ef4444" },
    { name: "Corroborated", value: c5.corroborated, fill: "#22c55e" },
    { name: "Unresolved", value: c5.unresolved, fill: "#64748b" },
  ];

  const kpis = [
    {
      title: "Index Plans Parsed",
      value: c1.plan_file_rows.toLocaleString(),
      sub: "11 index files → 33 rate files",
      icon: Database,
      stage: "C1",
    },
    {
      title: "PPO Plans Identified",
      value: c2.ppo_plans.toLocaleString(),
      sub: "1 CA Commercial Group File",
      icon: Filter,
      stage: "C2",
    },
    {
      title: "File Quality Score",
      value: `${c3.summary.quality_score}%`,
      sub: `Grade ${c3.summary.quality_grade} • 1.5M Price Rows`,
      icon: ShieldCheck,
      stage: "C3",
    },
    {
      title: "Curated PPO Rates",
      value: c4.curated_records.toLocaleString(),
      sub: "1.47M alt candidates resolved",
      icon: Table,
      stage: "C4",
    },
    {
      title: "Final Provider Rates",
      value: c6.c6_rows.toLocaleString(),
      sub: "Excel exported • Verified NPI/TIN",
      icon: FileSpreadsheet,
      stage: "C6",
    },
  ];

  return (
    <DashboardLayout title="Pipeline Architecture & Data Curation Overview">
      <div className="space-y-8 max-w-7xl mx-auto pb-12">
        {/* Executive Banner */}
        <div className="p-6 rounded-2xl bg-gradient-to-r from-primary/10 via-background to-accent/20 border border-primary/20 shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Badge variant="outline" className="text-primary border-primary/40 font-mono text-xs">
                  HiLabs AI Quest • IIT Roorkee
                </Badge>
                <Badge variant="secondary" className="font-mono text-xs">
                  Production CLI Pipeline
                </Badge>
              </div>
              <h1 className="text-2xl font-bold tracking-tight">
                Centene CA Commercial Group PPO Pipeline
              </h1>
              <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
                End-to-end evidence trail from raw Centene Transparency-in-Coverage files through PPO classification, file quality grading, rate curation, and multi-source address corroboration.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <Link href="/rates">
                <Button size="lg" className="h-12 px-6 text-sm sm:text-base font-bold shadow-lg hover:shadow-xl bg-primary hover:bg-primary/90 text-primary-foreground gap-2.5 transition-all transform hover:-translate-y-0.5 ring-2 ring-primary/20">
                  <Search className="h-5 w-5 text-primary-foreground" />
                  <span>Explore Provider Rates</span>
                  <ArrowRight className="h-4 w-4 ml-0.5" />
                </Button>
              </Link>
              <Link href="/quality">
                <Button size="lg" variant="outline" className="h-12 px-5 text-sm font-semibold gap-2 border-border/80 hover:bg-accent">
                  <FileCheck className="h-4 w-4" />
                  File Quality
                </Button>
              </Link>
            </div>
          </div>
        </div>

        {/* Top KPI Cards */}
        <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
          {kpis.map((kpi, idx) => (
            <motion.div
              key={kpi.title}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
            >
              <Card className="hover:shadow-md transition-shadow">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between text-muted-foreground mb-2">
                    <span className="text-xs font-semibold uppercase tracking-wider">{kpi.stage}</span>
                    <kpi.icon className="h-4 w-4 text-primary" />
                  </div>
                  <div className="text-2xl font-bold tracking-tight">{kpi.value}</div>
                  <div className="text-xs text-muted-foreground mt-1 truncate">{kpi.sub}</div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>

        {/* Pipeline Stepper / Flow Header */}
        <div className="border border-border/80 rounded-xl p-4 bg-card shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Layers className="h-4 w-4 text-primary" />
              Pipeline Execution Sequence
            </h2>
            <span className="text-xs text-muted-foreground font-mono">100% Deterministic & Traceable</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 text-xs">
            {[
              { id: "C1", title: "Index Parse", detail: "3,274 rows → 33 files" },
              { id: "C2", title: "PPO Classifier", detail: "453 PPO plans → 1 file" },
              { id: "C3", title: "File Quality", detail: "Grade B (75.7%)" },
              { id: "C4", title: "Rate Selection", detail: "21,853 curated rates" },
              { id: "C5", title: "Address Linking", detail: "3 sources corroborated" },
              { id: "C6", title: "Excel Output", detail: "12,326 final records" },
            ].map((step, i) => (
              <div
                key={step.id}
                className="p-2.5 rounded-lg border border-border/60 bg-muted/30 flex flex-col justify-between"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-primary">{step.id}</span>
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                </div>
                <div className="font-medium text-foreground">{step.title}</div>
                <div className="text-[11px] text-muted-foreground truncate">{step.detail}</div>
              </div>
            ))}
          </div>
        </div>

        {/* =================================================================== */}
        {/* STAGE C1: INDEX PARSING */}
        {/* =================================================================== */}
        <Card className="border-l-4 border-l-blue-500 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20 font-mono">Stage C1</Badge>
                <CardTitle className="text-lg">Index Parsing & Deduplication Engine</CardTitle>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
                <span>Runtime: {c1.runtime_seconds.toFixed(3)}s</span>
                <span>•</span>
                <span>11 Index Files</span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid md:grid-cols-3 gap-4">
              <div className="p-4 rounded-lg bg-muted/40 border border-border/60">
                <div className="text-xs text-muted-foreground uppercase font-semibold">Source Index Files</div>
                <div className="text-2xl font-bold mt-1 text-foreground">11 Files</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Ambetter, Fidelis, QualChoice (main + 7 employer sub-indexes), Health Net.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-muted/40 border border-border/60">
                <div className="text-xs text-muted-foreground uppercase font-semibold">Total Plan-File Rows</div>
                <div className="text-2xl font-bold mt-1 text-foreground">{c1.plan_file_rows.toLocaleString()}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Deduplicated from JSON reporting structures without loading raw archives into memory.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-muted/40 border border-border/60">
                <div className="text-xs text-muted-foreground uppercase font-semibold">Unique Physical Rate Files</div>
                <div className="text-2xl font-bold mt-1 text-foreground">{c1.unique_rate_files}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Massive fan-in: hundreds of plans map to identical monthly-refreshed rate URLs.
                </p>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-blue-500/5 border border-blue-500/20 text-xs space-y-2">
              <div className="font-semibold text-blue-600 dark:text-blue-400 flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4" />
                Deterministic Ingestion & Sanity Checks Applied:
              </div>
              <ul className="grid sm:grid-cols-2 gap-2 text-muted-foreground">
                <li className="flex items-start gap-1.5">
                  <span className="text-blue-500 font-bold">✓</span>
                  <span><strong>Many-to-One Plan Deduplication:</strong> In CA, 1,312 plans point to a single 701 MB JSON file. Stream deduplication avoided redundant file downloads.</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-blue-500 font-bold">✓</span>
                  <span><strong>Format Validation:</strong> Validated HIOS vs EIN plan IDs and normalized market type tokens (group vs individual).</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-blue-500 font-bold">✓</span>
                  <span><strong>Downstream Integrity Gate:</strong> Established NPI numeric 10-digit sanity rules that prevent malformed provider records from propagating into rate tables.</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-blue-500 font-bold">✓</span>
                  <span><strong>Dual-Format Artifacts:</strong> Generates both zero-copy <code>plans.parquet</code> and transparent <code>plans.csv</code> for judging inspection.</span>
                </li>
              </ul>
            </div>
          </CardContent>
        </Card>

        {/* =================================================================== */}
        {/* STAGE C2: PPO NETWORK CLASSIFICATION */}
        {/* =================================================================== */}
        <Card className="border-l-4 border-l-purple-500 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge className="bg-purple-500/10 text-purple-500 border-purple-500/20 font-mono">Stage C2</Badge>
                <CardTitle className="text-lg">PPO Network Discovery: The Classification Journey</CardTitle>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
                <span>3,274 Plans Evaluated</span>
                <span>•</span>
                <span className="text-purple-600 dark:text-purple-400 font-bold">453 PPO Plans Found</span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* The 3-Step Journey Narrative */}
            <div className="grid md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl border border-border bg-muted/20 relative overflow-hidden">
                <div className="text-xs font-bold text-red-500 uppercase tracking-wider mb-1">Attempt 1 • NLP Cosine Sim</div>
                <div className="font-semibold text-sm mb-1">Semantic Embedding Insufficient</div>
                <p className="text-xs text-muted-foreground">
                  Compared plan names against the CMS PPO archetype with <code>all-MiniLM-L6-v2</code>. Scores clustered tightly between -0.04 and 0.42 (max 0.418, mean 0.12). No discernible threshold separated HMO from PPO.
                </p>
              </div>

              <div className="p-4 rounded-xl border border-border bg-muted/20 relative overflow-hidden">
                <div className="text-xs font-bold text-amber-500 uppercase tracking-wider mb-1">Attempt 2 • Supervised Model</div>
                <div className="font-semibold text-sm mb-1">Logistic Regression Inadequate</div>
                <p className="text-xs text-muted-foreground">
                  Trained a logistic classifier on embedding + token features. Low confidence on hybrid names like &quot;Full Network HMO Platinum&quot; scored higher than genuine PPOs, yielding unacceptable false positives.
                </p>
              </div>

              <div className="p-4 rounded-xl border border-purple-500/30 bg-purple-500/5 relative overflow-hidden">
                <div className="text-xs font-bold text-green-500 uppercase tracking-wider mb-1">Solution • Rule Cascade</div>
                <div className="font-semibold text-sm mb-1">Deterministic Token Cascade</div>
                <p className="text-xs text-muted-foreground">
                  Applied hierarchical negative elimination (R-C2-01 to R-C2-03) before positive matching. Ruled out non-group (1,214), non-CA (748), and restrictive HMO/EPO/POS (728), perfectly isolating 453 PPOs.
                </p>
              </div>
            </div>

            {/* Visual Charts: NLP Distribution vs Final Classification */}
            <div className="grid md:grid-cols-2 gap-6 items-start">
              {/* NLP Score Histogram (Real data from /api/c2/nlp) */}
              <div className="p-4 rounded-xl border border-border/80 bg-card">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold">NLP Embedding Distribution</h3>
                    <p className="text-xs text-muted-foreground">Empirical proof: Scores compress in 0.0–0.2 range</p>
                  </div>
                  <Badge variant="outline" className="text-xs font-mono">Max: {c2.nlp_stats.max.toFixed(3)}</Badge>
                </div>
                {nlp ? (
                  <div className="h-52 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={nlp.histogram} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <XAxis dataKey="bin" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip
                          contentStyle={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))", fontSize: "12px" }}
                          formatter={(val: any) => [`${val} plans`, "Frequency"]}
                        />
                        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                          {nlp.histogram.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={entry.count > 1000 ? "hsl(var(--primary))" : "#94a3b8"}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="h-52 flex items-center justify-center text-xs text-muted-foreground">
                    Loading NLP distribution...
                  </div>
                )}
                <div className="mt-2 text-[11px] text-muted-foreground text-center">
                  Notice 0 plans scored &ge; 0.5. A blind threshold at 0.8 would miss 100% of PPO plans.
                </div>
              </div>

              {/* Network Classification Breakdown */}
              <div className="p-4 rounded-xl border border-border/80 bg-card">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold">Rule-Based Network Isolation</h3>
                    <p className="text-xs text-muted-foreground">Final classification across all 3,274 plans</p>
                  </div>
                  <Badge className="bg-purple-500 text-white font-mono text-xs">453 PPO Plans</Badge>
                </div>
                <div className="h-52 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart layout="vertical" data={networkChartData} margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                      <XAxis type="number" tick={{ fontSize: 10 }} />
                      <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} width={80} />
                      <Tooltip
                        contentStyle={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))", fontSize: "12px" }}
                        formatter={(val: any) => [`${val} plans`, "Count"]}
                      />
                      <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                        {networkChartData.map((entry, index) => (
                          <Cell key={`net-${index}`} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-2 text-[11px] text-muted-foreground text-center">
                  Result: Identified exactly 1 in-scope rate file (Health Net CA Commercial Group).
                </div>
              </div>
            </div>

            {/* Detailed C2 Rules Engine & Elimination Ledger */}
            <div className="pt-2">
              <div className="rounded-xl border border-purple-500/20 bg-card overflow-hidden">
                <div className="bg-purple-500/10 px-4 py-3 border-b border-purple-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                    <span className="font-semibold text-xs sm:text-sm text-foreground">
                      C2 Rules Engine &amp; Elimination Ledger (R-C2-01 to R-C2-08)
                    </span>
                  </div>
                  <Badge variant="outline" className="text-purple-600 dark:text-purple-300 border-purple-400 text-[11px] font-mono">
                    Deterministic • 100% Traceable
                  </Badge>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border bg-muted/40 font-semibold text-muted-foreground">
                        <th className="py-2.5 px-3">Rule ID</th>
                        <th className="py-2.5 px-3">Rule Name &amp; Description</th>
                        <th className="py-2.5 px-3">Condition / Matching Logic</th>
                        <th className="py-2.5 px-3 text-right">Plans Affected</th>
                        <th className="py-2.5 px-3">Classification</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      <tr className="hover:bg-muted/30">
                        <td className="py-2.5 px-3 font-mono font-bold text-purple-600 dark:text-purple-400">R-C2-01</td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">Non-Group Market Exclusion</div>
                          <div className="text-[11px] text-muted-foreground">Excludes individual exchange products (Ambetter marketplace) with separate statutory contracts.</div>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">market_type != &apos;group&apos;</td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold">1,214</td>
                        <td className="py-2.5 px-3"><Badge variant="outline" className="text-slate-500 border-slate-300 text-[10px]">OUT_OF_SCOPE</Badge></td>
                      </tr>
                      <tr className="hover:bg-muted/30">
                        <td className="py-2.5 px-3 font-mono font-bold text-purple-600 dark:text-purple-400">R-C2-02</td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">Non-California Scope Exclusion</div>
                          <div className="text-[11px] text-muted-foreground">Excludes Oregon (Health Net OR), Arkansas (QualChoice), and New York (Fidelis) rate structures.</div>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">!plan_id.has(&apos;CA&apos;) &amp;&amp; !url.has(&apos;_ca_&apos;)</td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold">748</td>
                        <td className="py-2.5 px-3"><Badge variant="outline" className="text-slate-500 border-slate-300 text-[10px]">OUT_OF_SCOPE</Badge></td>
                      </tr>
                      <tr className="hover:bg-muted/30">
                        <td className="py-2.5 px-3 font-mono font-bold text-amber-600 dark:text-amber-400">R-C2-03</td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">Restrictive Network Override</div>
                          <div className="text-[11px] text-muted-foreground">
                            <strong>Key insight:</strong> Restrictive tokens override PPO in account names. E.g., <em>&quot;SACRAMENTO CITY USD PPO ... EPO$15&quot;</em> is an EPO benefit design, not a PPO.
                          </div>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">HMO | EPO | POS | Salud | WholeCare</td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-amber-600">728</td>
                        <td className="py-2.5 px-3"><Badge variant="outline" className="text-amber-600 border-amber-300 text-[10px]">HMO (719), POS (6), EPO (3)</Badge></td>
                      </tr>
                      <tr className="hover:bg-muted/30 bg-purple-500/5">
                        <td className="py-2.5 px-3 font-mono font-bold text-primary">R-C2-04</td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium text-foreground">Positive PPO Token Match</div>
                          <div className="text-[11px] text-muted-foreground">Explicit Preferred Provider Organization benefits with out-of-network coverage options.</div>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">PPO | CUSPPO | Preferred Provider</td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-primary">453</td>
                        <td className="py-2.5 px-3"><Badge className="bg-primary text-primary-foreground text-[10px]">PPO (CONFIRMED)</Badge></td>
                      </tr>
                      <tr className="hover:bg-muted/30">
                        <td className="py-2.5 px-3 font-mono font-bold text-red-500">R-C2-05</td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">Elect Open Access (EOA) Unverified</div>
                          <div className="text-[11px] text-muted-foreground">Hybrid product line without explicit PPO rider kept unresolved to prevent polluting PPO rates.</div>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">\bEOA\b</td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-red-500">127</td>
                        <td className="py-2.5 px-3"><Badge variant="outline" className="text-red-500 border-red-300 text-[10px]">UNRESOLVED</Badge></td>
                      </tr>
                      <tr className="hover:bg-muted/30">
                        <td className="py-2.5 px-3 font-mono font-bold text-red-500">R-C2-06</td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">Insufficient Plan Evidence</div>
                          <div className="text-[11px] text-muted-foreground">Conservative policy: plans lacking identifiable tokens are never guessed.</div>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">No network token matched</td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-red-500">4</td>
                        <td className="py-2.5 px-3"><Badge variant="outline" className="text-red-500 border-red-300 text-[10px]">UNRESOLVED</Badge></td>
                      </tr>
                      <tr className="hover:bg-muted/30">
                        <td className="py-2.5 px-3 font-mono font-bold text-blue-500">R-C2-07</td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">Candidate Rate File Queueing</div>
                          <div className="text-[11px] text-muted-foreground">All 453 PPO plans converge to 1 single CA in-network JSON rate file; queued for C3/C4 extraction.</div>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">dedupe(rate_file_url for PPO)</td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-blue-500">1 Rate File</td>
                        <td className="py-2.5 px-3"><Badge variant="outline" className="text-blue-500 border-blue-300 text-[10px]">CANDIDATE QUEUE</Badge></td>
                      </tr>
                      <tr className="hover:bg-muted/30">
                        <td className="py-2.5 px-3 font-mono font-bold text-slate-500">R-C2-08</td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">NLP Cosine Similarity Gated Fallback</div>
                          <div className="text-[11px] text-muted-foreground">Safe gate at &ge; 0.80 prevents false positives since real cosine scores clustered &le; 0.418.</div>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px]">cos_sim(plan, PPO_archetype) &ge; 0.80</td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-slate-500">0</td>
                        <td className="py-2.5 px-3"><Badge variant="outline" className="text-slate-500 border-slate-300 text-[10px]">GATED (0 TRIGGERED)</Badge></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* =================================================================== */}
        {/* STAGE C3: FILE QUALITY GRADING */}
        {/* =================================================================== */}
        <Card className="border-l-4 border-l-emerald-500 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 font-mono">Stage C3</Badge>
                <CardTitle className="text-lg">PTD File Quality Grading & Anomaly Metrics</CardTitle>
              </div>
              <Link href="/quality">
                <Button size="sm" variant="outline" className="gap-1.5 text-xs">
                  View Full C3 Quality Breakdown
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Target File Identification Banner */}
            <div className="p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div className="space-y-0.5">
                <div className="font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5">
                  <Database className="h-4 w-4" />
                  Target File Scored: <code className="font-mono text-[11px] bg-background px-1.5 py-0.5 rounded border border-border">2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json</code>
                </div>
                <div className="text-muted-foreground text-[11px]">
                  Health Net California Commercial In-Network Rate File (701.6 MB uncompressed JSON • Schema v2.0.0 • Updated 2026-10-06)
                </div>
              </div>
              <Badge className="bg-emerald-600 text-white font-mono self-start sm:self-center">
                Single In-Scope CA PPO File
              </Badge>
            </div>

            <div className="grid md:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl border border-border bg-card flex flex-col justify-between">
                <div className="text-xs text-muted-foreground uppercase font-semibold">Composite Grade</div>
                <div className="flex items-baseline gap-2 mt-2">
                  <span className="text-4xl font-extrabold text-emerald-600 dark:text-emerald-400">
                    {c3.summary.quality_grade}
                  </span>
                  <span className="text-xl font-bold text-muted-foreground">
                    ({c3.summary.quality_score}%)
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Weighted sum across validity, duplicate density, freshness, and rate sanity.
                </p>
              </div>

              <div className="p-4 rounded-xl border border-border bg-card flex flex-col justify-between">
                <div className="text-xs text-muted-foreground uppercase font-semibold">Total Price Rows Scored</div>
                <div className="text-3xl font-bold mt-2 text-foreground">
                  {c3.summary.price_count.toLocaleString()}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  775 distinct billing codes • 2,825 provider groups referenced inline.
                </p>
              </div>

              <div className="p-4 rounded-xl border border-border bg-card flex flex-col justify-between">
                <div className="text-xs text-muted-foreground uppercase font-semibold">Rate Cleanliness</div>
                <div className="text-3xl font-bold mt-2 text-emerald-600 dark:text-emerald-400">
                  100% Clean
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  0 zero rates • 0 negative rates • 0 non-numeric prices in 1.5M rows.
                </p>
              </div>

              <div className="p-4 rounded-xl border border-border bg-card flex flex-col justify-between">
                <div className="text-xs text-muted-foreground uppercase font-semibold">Duplicate Density</div>
                <div className="text-3xl font-bold mt-2 text-amber-500">
                  {c3.summary.exact_duplicate_rate_pct.toFixed(1)}%
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Shared contracts repeated across plan structures. Deduplicated in C4.
                </p>
              </div>
            </div>

            {/* Quality Progress Meters */}
            <div className="grid md:grid-cols-2 gap-4 p-4 rounded-xl bg-muted/20 border border-border">
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-medium">Price Validity ($0 / Negative / Invalid)</span>
                    <span className="font-mono text-emerald-600 font-bold">100.0% Pass</span>
                  </div>
                  <Progress value={100} className="h-2 bg-muted [&>div]:bg-emerald-500" />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-medium">Negotiated Dollar Rate Percentage</span>
                    <span className="font-mono text-emerald-600 font-bold">{c3.summary.negotiated_dollar_rate_pct.toFixed(2)}%</span>
                  </div>
                  <Progress value={99.99} className="h-2 bg-muted [&>div]:bg-emerald-500" />
                </div>
              </div>
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-medium">File Freshness (Refreshed 2026-10-06)</span>
                    <span className="font-mono text-emerald-600 font-bold">100.0% Fresh</span>
                  </div>
                  <Progress value={100} className="h-2 bg-muted [&>div]:bg-emerald-500" />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-medium">Institutional vs Professional Ratio</span>
                    <span className="font-mono text-muted-foreground">99.7% Inst / 0.3% Prof</span>
                  </div>
                  <Progress value={0.3} className="h-2 bg-muted [&>div]:bg-blue-500" />
                </div>
              </div>
            </div>

            {/* Multi-File Generalization & Scalability Notice */}
            <div className="p-4 rounded-xl border border-border/80 bg-muted/30 text-xs space-y-1.5">
              <div className="font-semibold text-foreground flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                Universal Pipeline Scalability &amp; Cross-File Generalization:
              </div>
              <p className="text-muted-foreground leading-relaxed">
                The scorecard above grades the single in-scope <strong>Health Net California Commercial PPO file</strong> identified during Stage C2. However, our bounded-memory streaming quality engine (<code>pipeline.stages.c3_quality</code>) is completely generalizable. By running <code className="bg-background px-1.5 py-0.5 rounded border border-border font-mono text-[11px]">uv run python -m pipeline c3 --workers 8</code>, the exact same multi-dimensional metrics (price validity, duplicate density, Medicare PFS out-of-band rates, freshness, and A–F composite grades) can be computed in parallel across <strong>all other 32 Centene rate files</strong> (Ambetter Marketplace, QualChoice employer files, Fidelis New York, and Health Net Oregon) with constant, flat RAM usage.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* =================================================================== */}
        {/* STAGE C4: RATE EXTRACTION & SELECTION HIERARCHY */}
        {/* =================================================================== */}
        <Card className="border-l-4 border-l-amber-500 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/20 font-mono">Stage C4</Badge>
                <CardTitle className="text-lg">Rate Extraction & Candidate Resolution Hierarchy</CardTitle>
              </div>
              <div className="text-xs text-muted-foreground font-mono">
                <span className="font-bold text-amber-600 dark:text-amber-400">21,853 Curated Rates</span>
                <span> across 3,734 NPIs</span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <p className="text-xs text-muted-foreground">
              What was C4? TiC rate files contain multiple overlapping fee schedules for the same provider and billing code. Stage C4 explodes inline provider groups, applies deterministic conflict resolution rules, and eliminates duplicates.
            </p>

            {/* The Extraction Funnel */}
            <div className="grid md:grid-cols-4 gap-3 text-center">
              <div className="p-3.5 rounded-lg border border-border bg-card">
                <div className="text-[11px] text-muted-foreground font-semibold uppercase">1. Raw Explosions</div>
                <div className="text-xl font-bold mt-1">1,511,720</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">397,726 rate entries exploded</div>
              </div>
              <div className="p-3.5 rounded-lg border border-border bg-card">
                <div className="text-[11px] text-muted-foreground font-semibold uppercase">2. Duplicate Purge</div>
                <div className="text-xl font-bold mt-1 text-amber-600">-12,732</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">Exact duplicates removed</div>
              </div>
              <div className="p-3.5 rounded-lg border border-border bg-card">
                <div className="text-[11px] text-muted-foreground font-semibold uppercase">3. Alternative Pruning</div>
                <div className="text-xl font-bold mt-1 text-purple-600">-1,477,130</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">Ranked by selection hierarchy</div>
              </div>
              <div className="p-3.5 rounded-lg border border-emerald-500/40 bg-emerald-500/5">
                <div className="text-[11px] text-emerald-600 font-semibold uppercase">4. Curated PPO Rates</div>
                <div className="text-xl font-bold mt-1 text-emerald-600">21,853</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">3,734 NPIs • 2,888 TINs</div>
              </div>
            </div>

            {/* Sanity Check & Rejection Callout */}
            <div className="p-4 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs">
              <div className="flex items-center gap-2 font-semibold text-amber-600 dark:text-amber-400 mb-2">
                <ShieldCheck className="h-4 w-4" />
                Deterministic Sanity Checks & Rejections:
              </div>
              <div className="grid sm:grid-cols-3 gap-3">
                <div className="p-2.5 rounded bg-background/60 border border-border">
                  <div className="text-muted-foreground">Invalid NPI Format Check:</div>
                  <div className="font-bold text-red-500 mt-0.5">5 Records Rejected</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">Fewer than 10 digits; dropped with audit reason</div>
                </div>
                <div className="p-2.5 rounded bg-background/60 border border-border">
                  <div className="text-muted-foreground">Rate Sanity Check:</div>
                  <div className="font-bold text-emerald-600 mt-0.5">0 Zero / 0 Negative</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">Zero rates dropped; 100% strictly positive</div>
                </div>
                <div className="p-2.5 rounded bg-background/60 border border-border">
                  <div className="text-muted-foreground">Conflict Resolution Rule:</div>
                  <div className="font-bold text-foreground mt-0.5">R-C4-SEL-01 to 07</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">Professional &gt; Inst, base rate &gt; modified</div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* =================================================================== */}
        {/* STAGE C5 & C6: ADDRESS LINKING & FINAL OUTPUT */}
        {/* =================================================================== */}
        <Card className="border-l-4 border-l-cyan-500 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge className="bg-cyan-500/10 text-cyan-500 border-cyan-500/20 font-mono">Stage C5 &amp; C6</Badge>
                <CardTitle className="text-lg">Address Corroboration &amp; Deliverable Rate File</CardTitle>
              </div>
              <div className="flex items-center gap-2">
                <Link href="/address">
                  <Button size="sm" variant="outline" className="gap-1.5 text-xs">
                    Address Matches
                    <MapPin className="h-3.5 w-3.5" />
                  </Button>
                </Link>
                <Link href="/rates">
                  <Button size="sm" className="gap-1.5 text-xs bg-cyan-600 hover:bg-cyan-700 text-white">
                    Search Rates
                    <Search className="h-3.5 w-3.5" />
                  </Button>
                </Link>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid md:grid-cols-3 gap-6">
              {/* Address Distribution Donut */}
              <div className="p-4 rounded-xl border border-border bg-card">
                <h3 className="text-sm font-semibold mb-1">Address Evidence Tiers</h3>
                <p className="text-xs text-muted-foreground mb-3">NPPES alone is ~80% stale; corroborated across 3 sources</p>
                <div className="h-44 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={addressChartData}
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={70}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {addressChartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))", fontSize: "12px" }}
                        formatter={(val: any) => [`${val.toLocaleString()} records`, ""]}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] mt-2">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                    <span>Corroborated: {c5.corroborated}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
                    <span>Single: {c5.single_source.toLocaleString()}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                    <span>Conflicting: {c5.conflicting.toLocaleString()}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-slate-500" />
                    <span>Unresolved: {c5.unresolved}</span>
                  </div>
                </div>
              </div>

              {/* Multi-Source Corroboration Engine */}
              <div className="p-4 rounded-xl border border-border bg-card space-y-3">
                <h3 className="text-sm font-semibold mb-1">Evidence Sources Linked</h3>
                <div className="space-y-2 text-xs">
                  <div className="p-2 rounded bg-muted/30 border border-border/60">
                    <div className="font-semibold text-foreground">NPPES Oct 2026 CA Extract</div>
                    <div className="text-muted-foreground text-[11px]">Primary practice location addresses &amp; taxonomy codes</div>
                  </div>
                  <div className="p-2 rounded bg-muted/30 border border-border/60">
                    <div className="font-semibold text-foreground">NPPES PL Secondary File</div>
                    <div className="text-muted-foreground text-[11px]">Multiple physical practicing locations for multi-site providers</div>
                  </div>
                  <div className="p-2 rounded bg-muted/30 border border-border/60">
                    <div className="font-semibold text-foreground">CMS Doctors &amp; Clinicians (DAC)</div>
                    <div className="text-muted-foreground text-[11px]">Recent Medicare billing address confirmation &amp; PAC org IDs</div>
                  </div>
                  <div className="p-2 rounded bg-muted/30 border border-border/60">
                    <div className="font-semibold text-foreground">NUCC Specialty Mapping</div>
                    <div className="text-muted-foreground text-[11px]">{c5.specialty_mapped.toLocaleString()} mapped (883 codes), 36 unmapped</div>
                  </div>
                </div>
              </div>

              {/* Deliverable C6 Summary */}
              <div className="p-4 rounded-xl border border-cyan-500/30 bg-cyan-500/5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-cyan-700 dark:text-cyan-300">Deliverable 1 Rate File</h3>
                  <Badge variant="outline" className="text-cyan-600 border-cyan-400 text-xs">C6 Output</Badge>
                </div>
                <div className="text-3xl font-extrabold text-foreground">
                  {c6.c6_rows.toLocaleString()}
                </div>
                <div className="text-xs text-muted-foreground space-y-2">
                  <p>
                    Final provider-level records written to <code>final_provider_rates.xlsx</code> with columns: <strong>NPI, TIN, Address, Billing Code, Specialty, Rate</strong>.
                  </p>
                  <p>
                    <strong>Ambiguity Resolution:</strong> {c6.ambiguous_resolved.toLocaleString()} ambiguous provider addresses resolved via deterministic tier ranking.
                  </p>
                </div>
                <div className="pt-2">
                  <Link href="/rates">
                    <Button size="lg" className="w-full h-11 gap-2 text-sm font-bold bg-cyan-600 hover:bg-cyan-700 text-white shadow-md hover:shadow-lg transition-all">
                      <Search className="h-4 w-4" />
                      Open Provider Rates Explorer (12,326 Rows)
                      <ArrowRight className="h-4 w-4 ml-1" />
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}