"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  FileCheck,
  AlertTriangle,
  CheckCircle,
  XCircle,
  MinusCircle,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { KPICard } from "@/components/dashboard/KPICard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { getFileQualityData } from "@/lib/api/data";
import type { FileQualityData } from "@/lib/types";

const gradeColors = {
  A: "bg-emerald-600 text-white shadow-md",
  B: "bg-blue-600 text-white shadow-md",
  C: "bg-yellow-500 text-slate-950 font-black shadow-md",
  D: "bg-orange-500 text-white shadow-md",
  F: "bg-red-600 text-white shadow-md",
};

const gradeBgColors = {
  A: "bg-green-500/10 border-green-500/20",
  B: "bg-blue-500/10 border-blue-500/20",
  C: "bg-yellow-500/10 border-yellow-500/20",
  D: "bg-orange-500/10 border-orange-500/20",
  F: "bg-red-500/10 border-red-500/20",
};

const statusIcons = {
  pass: CheckCircle,
  warn: AlertTriangle,
  fail: XCircle,
};

const statusColors = {
  pass: "text-green-500",
  warn: "text-yellow-500",
  fail: "text-red-500",
};

export default function QualityPage() {
  const [data, setData] = useState<FileQualityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const response = await fetch("/api/quality");
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

  if (loading) {
    return (
      <DashboardLayout title="File Quality">
        <div className="space-y-6" role="status" aria-label="Loading file quality data">
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardContent className="p-6 text-center">
                <Skeleton className="h-16 w-16 rounded-full mx-auto mb-4" />
                <Skeleton className="h-4 w-24 mx-auto" />
                <Skeleton className="h-3 w-32 mx-auto mt-2" />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">Metrics</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="flex items-center gap-4">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-4 w-20" />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">Outliers</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[...Array(3)].map((_, i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout title="File Quality">
        <div className="text-center py-12">
          <p className="text-red-500">Error loading data: {error}</p>
        </div>
      </DashboardLayout>
    );
  }

  if (!data) return null;

  const { grade, score, metrics, outliers } = data;

  return (
    <DashboardLayout title="File Quality">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="space-y-6"
      >
        {/* Target File Identification & Universal Extensibility Banner */}
        <div className="p-5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-3 text-xs">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-2 text-sm sm:text-base">
                <FileCheck className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                Target File Graded: <code className="font-mono text-xs bg-background px-2 py-0.5 rounded border border-border">2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json</code>
              </div>
              <div className="text-muted-foreground text-xs">
                Entity: Health Net California (Third Party Administrator) • 701.6 MB uncompressed JSON • Schema v2.0.0 • Updated 2026-10-06
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge className="bg-emerald-600 text-white font-mono">
                California PPO Candidate File
              </Badge>
            </div>
          </div>

          <div className="pt-2 border-t border-emerald-500/20 text-muted-foreground text-[11px] leading-relaxed">
            <span className="font-semibold text-foreground">Why this file?</span> In Stage C2, all 453 identified California Commercial Group PPO plans converged to this single in-network JSON rate file.
            <span className="font-semibold text-foreground ml-2">Universal Quality Pipeline:</span> The exact same bounded-memory streaming quality engine (<code className="font-mono text-[10px] bg-background px-1 py-0.5 rounded border border-border">pipeline.stages.c3_quality</code>) can be executed across <strong>all other 32 Centene rate files</strong> (Ambetter Marketplace, QualChoice employer files, Fidelis New York, and Health Net Oregon) via <code className="font-mono text-[10px] bg-background px-1.5 py-0.5 rounded border border-border text-foreground">uv run python -m pipeline c3 --workers N</code>, outputting identical standardized metrics, anomaly detection, and composite A–F quality grades.
          </div>
        </div>

        {/* Grade Card */}
        <Card className={cn("border-2", gradeBgColors[grade as keyof typeof gradeBgColors])}>
          <CardContent className="p-8">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
              <div className="flex items-center gap-6">
                <div
                  className={cn(
                    "flex items-center justify-center w-24 h-24 rounded-2xl font-bold text-4xl",
                    gradeColors[grade as keyof typeof gradeColors]
                  )}
                >
                  {grade}
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Overall File Grade</p>
                  <p className="text-3xl font-bold">C3 Quality Score: {score}%</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <p className="text-2xl font-bold tabular-nums">{metrics.find(m => m.name === "Exact Duplicates")?.value || 0}</p>
                  <p className="text-xs text-muted-foreground">Exact Duplicates</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold tabular-nums">{metrics.find(m => m.name === "Alternative Candidates Removed")?.value || 0}</p>
                  <p className="text-xs text-muted-foreground">Alt. Candidates</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold tabular-nums">{metrics.find(m => m.name === "Records Rejected")?.value || 0}</p>
                  <p className="text-xs text-muted-foreground">Rejected</p>
                </div>
              </div>
            </div>
            <div className="mt-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Quality Score Progress</span>
                <span className="text-sm font-mono tabular-nums">{score}%</span>
              </div>
              <Progress value={score} className="h-3" />
            </div>
          </CardContent>
        </Card>

        {/* Metrics Table & Outliers */}
        <div className="grid gap-6 md:grid-cols-2">
          {/* Metrics */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <FileCheck className="h-4 w-4" />
                Quality Metrics
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {metrics.map((metric, index) => {
                const StatusIcon = statusIcons[metric.status];
                return (
                  <motion.div
                    key={metric.name}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3, delay: index * 0.05 }}
                    className="flex items-center justify-between p-3 bg-muted/30 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      <StatusIcon className={cn("h-5 w-5", statusColors[metric.status])} />
                      <div>
                      <p className="font-medium">{metric.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {typeof metric.value === "number" ? metric.value.toLocaleString() : metric.value}
                      </p>
                    </div>
                  </div>
                  <Badge
                    variant={
                      metric.status === "pass"
                        ? "default"
                        : metric.status === "warn"
                        ? "secondary"
                        : "destructive"
                    }
                    className="text-sm px-3 py-1"
                  >
                    {metric.status.charAt(0).toUpperCase() + metric.status.slice(1)}
                  </Badge>
                </motion.div>
              );
            })}
            </CardContent>
          </Card>

          {/* Outliers */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Outlier Breakdown
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {outliers.map((outlier, index) => (
                <motion.div
                  key={outlier.type}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: index * 0.05 }}
                  className="p-4 bg-muted/30 rounded-lg"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "w-3 h-3 rounded-full",
                          outlier.severity === "high" && "bg-red-500",
                          outlier.severity === "medium" && "bg-yellow-500",
                          outlier.severity === "low" && "bg-green-500"
                        )}
                      />
                      <span className="font-medium">{outlier.type}</span>
                    </div>
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
                  </div>
                  <div className="flex items-center justify-between">
                    <Progress
                      value={Math.min((outlier.count / 1500000) * 100, 100)}
                      className="h-2 flex-1 mr-4"
                    />
                    <span className="font-mono font-semibold text-lg tabular-nums">
                      {outlier.count.toLocaleString()}
                    </span>
                  </div>
                </motion.div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Detailed Metrics Grid */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Detailed Metrics
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {metrics.map((metric, index) => (
                <motion.div
                  key={metric.name}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.2 + index * 0.05 }}
                  className="p-4 bg-muted/30 rounded-lg"
                >
                  <p className="text-sm text-muted-foreground mb-1">{metric.name}</p>
                  <p className="text-2xl font-bold tabular-nums">
                    {typeof metric.value === "number" ? metric.value.toLocaleString() : metric.value}
                  </p>
                  <Badge
                    variant={
                      metric.status === "pass"
                        ? "default"
                        : metric.status === "warn"
                        ? "secondary"
                        : "destructive"
                    }
                    className="mt-2 text-xs"
                  >
                    {metric.status}
                  </Badge>
                </motion.div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Multi-File Generalization & Scalability Notice */}
        <Card className="border-border/80 bg-muted/20">
          <CardContent className="p-6">
            <div className="flex items-start gap-3">
              <FileCheck className="h-5 w-5 text-emerald-600 dark:text-emerald-400 mt-0.5 flex-shrink-0" />
              <div className="space-y-1.5 text-xs">
                <h4 className="font-semibold text-sm text-foreground">
                  Universal Multi-File Quality Pipeline (Linear Scalability)
                </h4>
                <p className="text-muted-foreground leading-relaxed">
                  The metrics and grade displayed above reflect our analysis of the single in-scope <strong>Health Net California Commercial PPO file</strong> (<code className="font-mono text-[11px] bg-background px-1 py-0.5 rounded border border-border">...healthnet-ca_in-network.json</code>). However, our streaming quality architecture (<code className="font-mono text-[11px] bg-background px-1 py-0.5 rounded border border-border">pipeline.stages.c3_quality</code>) is completely generalized and file-agnostic.
                </p>
                <p className="text-muted-foreground leading-relaxed">
                  By running <code className="font-mono text-[11px] bg-background px-1.5 py-0.5 rounded border border-border text-foreground">uv run python -m pipeline c3 --workers N</code>, the exact same comprehensive metrics (zero/negative price checks, exact duplicate rate detection, freshness scoring, and CMS Medicare PFS out-of-band ratio) can be executed across <strong>all 33 Centene rate files</strong> (Ambetter, QualChoice, Fidelis NY, Health Net OR) in parallel with bounded memory consumption.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </DashboardLayout>
  );
}