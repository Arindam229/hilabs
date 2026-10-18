"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import {
  Activity,
  Users,
  Building2,
  MapPin,
  FileText,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { KPICard } from "@/components/dashboard/KPICard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  getKPIData,
  getPipelineStages,
  getAddressStatusData,
  getFileQualityData,
} from "@/lib/api/data";
import type {
  KPIData,
  PipelineStage,
  AddressStatusData,
  FileQualityData,
} from "@/lib/types";

interface OverviewData {
  kpi: KPIData;
  pipeline: PipelineStage[];
  addressStatus: AddressStatusData;
  fileQuality: FileQualityData;
}

export default function OverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [c2, setC2] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const response = await fetch("/api/data");
        if (!response.ok) throw new Error("Failed to fetch data");
        const json = await response.json();
        setData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  useEffect(() => {
    fetch("/api/c2").then((r) => r.ok ? r.json() : null).then((j) => { if (j) { console.log("C2", j); setC2(j); } }).catch((e) => console.error("C2 fetch", e));
  }, []);

  if (loading) {
    return (
      <DashboardLayout title="Overview" pipelineStages={[]}>
        <div className="space-y-6" role="status" aria-label="Loading dashboard">
          {/* KPI Cards Skeleton */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            {[...Array(5)].map((_, i) => (
              <Card key={i} className="overflow-hidden">
                <CardContent className="p-5">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-8 w-1/2 mt-2" />
                  <Skeleton className="h-3 w-1/4 mt-2" />
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Pipeline Status Skeleton */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Pipeline Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4 overflow-x-auto pb-2">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="flex flex-col items-center gap-2 min-w-[100px]">
                    <Skeleton className="h-10 w-10 rounded-full" />
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-3 w-3/4" />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Charts Skeleton */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">Address Coverage</CardTitle>
              </CardHeader>
              <CardContent>
                <Skeleton className="h-64 w-full" />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">File Quality Grade</CardTitle>
              </CardHeader>
              <CardContent>
                <Skeleton className="h-64 w-full" />
              </CardContent>
            </Card>
          </div>
        </div>
        {/* C2 Network Summary */}
      {c2 ? (
        <Card>
          <CardHeader>
            <CardTitle>C2 PPO Network Classification</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {Object.entries(c2.network_type_counts || {}).map(([k, v]) => (
                <div key={k} className="rounded-lg border p-3">
                  <div className="text-xs text-muted-foreground">{k}</div>
                  <div className="text-xl font-bold tabular-nums">{Number(v).toLocaleString()}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 text-sm text-muted-foreground">
              Confidence: {Object.entries(c2.confidence_counts || {}).map(([k,v]) => `${k}: ${v}`).join(" · ")}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">
              NLP score range: {c2.nlp_score_min?.toFixed(3)} – {c2.nlp_score_max?.toFixed(3)} (mean {c2.nlp_score_mean?.toFixed(3)})
            </div>
            <div className="h-40 mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={Object.entries(c2.confidence_counts || {}).map(([k,v]) => ({name:k, value:v}))}>
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="value" fill="#3B82F6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card><CardContent className="p-6 text-muted-foreground">Loading C2 network data…</CardContent></Card>
      )}
    </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout title="Overview" pipelineStages={[]}>
        <div className="text-center py-12">
          <p className="text-red-500">Error loading dashboard: {error}</p>
        </div>
      </DashboardLayout>
    );
  }

  if (!data) {
    return null;
  }

  const { kpi, pipeline, addressStatus, fileQuality } = data;

  const kpiCards = [
    {
      title: "Rates Extracted",
      value: kpi.ratesExtracted.toLocaleString(),
      description: "Total negotiated rates processed",
      icon: <Activity className="h-5 w-5" />,
      trend: { value: 12.5, label: "vs last run" },
    },
    {
      title: "Unique NPIs",
      value: kpi.npis.toLocaleString(),
      description: "Distinct providers in dataset",
      icon: <Users className="h-5 w-5" />,
      trend: { value: 3.2, label: "vs last run" },
    },
    {
      title: "Unique TINs",
      value: kpi.tins.toLocaleString(),
      description: "Distinct tax ID numbers",
      icon: <Building2 className="h-5 w-5" />,
      trend: { value: 1.8, label: "vs last run" },
    },
    {
      title: "Verified Addresses",
      value: `${kpi.verifiedAddressesPct}%`,
      description: "Corroborated + single source",
      icon: <MapPin className="h-5 w-5" />,
      trend: { value: -0.5, label: "vs last run" },
    },
    {
      title: "File Grade",
      value: kpi.fileGrade,
      description: `Quality score: ${fileQuality.score}%`,
      icon: <FileText className="h-5 w-5" />,
      trend: { value: 0, label: "stable" },
    },
  ];

  const stageColors = {
    completed: "text-green-500 bg-green-500/10",
    running: "text-blue-500 bg-blue-500/10 animate-pulse",
    pending: "text-muted-foreground bg-muted",
    failed: "text-red-500 bg-red-500/10",
  };

  const stageIcons = {
    completed: "✓",
    running: "◐",
    pending: "○",
    failed: "✗",
  };

  return (
    <DashboardLayout
      title="Overview"
      pipelineStages={pipeline}
    >
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="space-y-6"
      >
        {/* KPI Cards */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
          {kpiCards.map((kpi, index) => (
            <motion.div
              key={kpi.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.05 }}
            >
              <KPICard {...kpi} />
            </motion.div>
          ))}
        </div>

        {/* Pipeline Status & Quick Stats */}
        <div className="grid gap-4 md:grid-cols-3">
          {/* Pipeline Status */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.2 }}
            className="md:col-span-2"
          >
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Activity className="h-4 w-4" />
                  Pipeline Status
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="flex items-center gap-4 overflow-x-auto p-4">
                  {pipeline.map((stage, index) => (
                    <motion.div
                      key={stage.stage}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3, delay: index * 0.05 }}
                      className="flex flex-col items-center gap-2 min-w-[120px] relative"
                    >
                      {index > 0 && (
                        <div className="absolute left-[-24px] top-5 w-4 h-0.5 bg-border" />
                      )}
                      <div
                        className={cn(
                          "flex items-center justify-center w-10 h-10 rounded-full font-medium text-sm",
                          stageColors[stage.status]
                        )}
                      >
                        {stageIcons[stage.status]}
                      </div>
                      <div className="text-center">
                        <p className="text-xs font-medium truncate w-[120px]">{stage.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {stage.runtime_seconds ? `${stage.runtime_seconds.toFixed(1)}s` : "—"}
                        </p>
                        {stage.records_out !== undefined && (
                          <p className="text-xs text-muted-foreground font-mono">
                            {stage.records_out.toLocaleString()} out
                          </p>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* File Quality Summary */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.25 }}
          >
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  File Quality
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Overall Grade</span>
                  <Badge
                    variant={
                      fileQuality.grade === "A"
                        ? "default"
                        : fileQuality.grade === "B"
                        ? "secondary"
                        : fileQuality.grade === "C"
                        ? "outline"
                        : "destructive"
                    }
                    className="text-lg px-3 py-1"
                  >
                    {fileQuality.grade}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">C3 Quality Score</span>
                  <span className="font-mono font-semibold">{fileQuality.score}%</span>
                </div>
                <Separator />
                <div className="space-y-2 text-sm">
                  {fileQuality.metrics.slice(0, 4).map((metric, i) => (
                    <div key={i} className="flex items-center justify-between">
                      <span className="text-muted-foreground truncate pr-2">{metric.name}</span>
                      <Badge
                        variant={
                          metric.status === "pass"
                            ? "default"
                            : metric.status === "warn"
                            ? "secondary"
                            : "destructive"
                        }
                        className="text-xs"
                      >
                        {metric.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* Address Coverage Donut & Outliers */}
        <div className="grid gap-4 md:grid-cols-2">
          {/* Address Coverage */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.3 }}
          >
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <MapPin className="h-4 w-4" />
                  Address Coverage
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-center h-48">
                  {/* Simple donut chart using conic gradient */}
                  <div className="relative w-48 h-48">
                    <div
                      className="w-full h-full rounded-full"
                      style={{
                        background: `conic-gradient(
                          hsl(var(--status-corroborated)) 0deg ${
                            (addressStatus.corroborated / addressStatus.total) * 360
                          }deg,
                          hsl(var(--status-single)) ${
                            (addressStatus.corroborated / addressStatus.total) * 360
                          }deg ${
                            ((addressStatus.corroborated + addressStatus.single_source) /
                              addressStatus.total) *
                            360
                          }deg,
                          hsl(var(--status-conflicting)) ${
                            ((addressStatus.corroborated + addressStatus.single_source) /
                              addressStatus.total) *
                            360
                          }deg ${
                            ((addressStatus.corroborated +
                              addressStatus.single_source +
                              addressStatus.conflicting) /
                              addressStatus.total) *
                            360
                          }deg,
                          hsl(var(--status-unresolved)) ${
                            ((addressStatus.corroborated +
                              addressStatus.single_source +
                              addressStatus.conflicting) /
                              addressStatus.total) *
                            360
                          }deg 360deg
                        )`,
                      }}
                    >
                      <div className="w-[70%] h-[70%] rounded-full bg-background absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center">
                        <span className="text-2xl font-bold">
                          {addressStatus.total > 0
                            ? Math.round(
                                ((addressStatus.corroborated + addressStatus.single_source) /
                                  addressStatus.total) *
                                  100
                              )
                            : 0}%
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-center gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: `hsl(var(--status-corroborated))` }}
                    />
                    <span>Corroborated: {addressStatus.corroborated}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: `hsl(var(--status-single))` }}
                    />
                    <span>Single: {addressStatus.single_source}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: `hsl(var(--status-conflicting))` }}
                    />
                    <span>Conflicting: {addressStatus.conflicting}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: `hsl(var(--status-unresolved))` }}
                    />
                    <span>Unresolved: {addressStatus.unresolved}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* Outlier Breakdown */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.35 }}
          >
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  Outlier Breakdown
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {fileQuality.outliers.map((outlier, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "w-2 h-2 rounded-full",
                          outlier.severity === "high" && "bg-red-500",
                          outlier.severity === "medium" && "bg-yellow-500",
                          outlier.severity === "low" && "bg-green-500"
                        )}
                      />
                      <span className="font-medium">{outlier.type}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge
                        variant={
                          outlier.severity === "high"
                            ? "destructive"
                            : outlier.severity === "medium"
                            ? "secondary"
                            : "outline"
                        }
                        className="text-xs"
                      >
                        {outlier.severity}
                      </Badge>
                      <span className="font-mono font-semibold text-lg">{outlier.count.toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </motion.div>
        </div>
      </motion.div>
    </DashboardLayout>
  );
}