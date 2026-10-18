"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  GitBranch,
  Clock,
  Database,
  FileText,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  AlertCircle,
  Loader2,
  XCircle,
} from "lucide-react";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { getAuditTrail } from "@/lib/api/data";
import type { AuditEntry } from "@/lib/types";

const stageLabels: Record<string, string> = {
  c1: "C1: Index Parse",
  c2: "C2: PPO Classification",
  c3: "C3: File Quality",
  c4: "C4: Rate Selection",
  c5: "C5: Address Linking",
  c6: "C6: Provider Rates",
};

const stageIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  c1: Database,
  c2: FileText,
  c3: FileText,
  c4: Database,
  c5: FileText,
  c6: GitBranch,
};

export default function AuditPage() {
  const [data, setData] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedStage, setExpandedStage] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const response = await fetch("/api/audit");
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
      <DashboardLayout title="Audit Trail">
        <div className="space-y-4" role="status" aria-label="Loading audit trail">
          {[...Array(6)].map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="flex items-center gap-4">
                  <Skeleton className="h-10 w-10 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-1/4" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout title="Audit Trail">
        <div className="text-center py-12">
          <p className="text-red-500">Error loading data: {error}</p>
        </div>
      </DashboardLayout>
    );
  }

  const getStatus = (entry: AuditEntry) => {
    // All stages are completed in the mock data
    return "completed";
  };

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleString("en-US", { timeZone: "UTC" });
    } catch {
      return dateString;
    }
  };

  return (
    <DashboardLayout title="Audit Trail">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="space-y-4"
      >
        {/* Summary */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2">
              <GitBranch className="h-4 w-4" />
              Pipeline Execution Summary
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="p-4 bg-muted/50 rounded-lg">
                <p className="text-sm text-muted-foreground">Total Stages</p>
                <p className="text-2xl font-bold">{data.length}</p>
              </div>
              <div className="p-4 bg-muted/50 rounded-lg">
                <p className="text-sm text-muted-foreground">Total Runtime</p>
                <p className="text-2xl font-bold tabular-nums">
                  {data.reduce((sum, d) => sum + (d.runtime_seconds || 0), 0).toFixed(1)}s
                </p>
              </div>
              <div className="p-4 bg-muted/50 rounded-lg">
                <p className="text-sm text-muted-foreground">Git Commit</p>
                <p className="text-2xl font-bold font-mono text-sm">
                  {data[0]?.git_sha || "—"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Timeline */}
        <div className="space-y-4">
          {data.map((entry, index) => {
            const Icon = stageIcons[entry.stage] || GitBranch;
            const status = getStatus(entry);
            const isExpanded = expandedStage === entry.stage;

            return (
              <motion.div
                key={entry.stage}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: index * 0.05 }}
              >
                <Card className="overflow-hidden">
                  <CardContent className="p-0">
                    <Collapsible open={isExpanded} onOpenChange={(open) => setExpandedStage(open ? entry.stage : null)}>
                      <CollapsibleTrigger className="w-full p-4 hover:bg-muted/50 transition-colors">
                        <div className="flex items-center gap-4 w-full">
                          {/* Timeline dot and line */}
                          <div className="relative flex-shrink-0">
                            <div
                              className={cn(
                                "w-3 h-3 rounded-full border-4 flex-shrink-0",
                                status === "completed" && "bg-green-500 border-green-500",
                                status === "running" && "bg-blue-500 border-blue-500 animate-pulse",
                                status === "pending" && "bg-transparent border-muted-foreground/50",
                                status === "failed" && "bg-red-500 border-red-500"
                              )}
                            />
                            {index < data.length - 1 && (
                              <div className="absolute left-1.5 top-7 w-0.5 h-full bg-border" />
                            )}
                          </div>

                          {/* Stage info */}
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            <div
                              className={cn(
                                "flex items-center justify-center w-10 h-10 rounded-lg",
                                status === "completed" && "bg-green-500/10 text-green-500",
                                status === "running" && "bg-blue-500/10 text-blue-500",
                                status === "pending" && "bg-muted text-muted-foreground",
                                status === "failed" && "bg-red-500/10 text-red-500"
                              )}
                            >
                              <Icon className="h-5 w-5" />
                            </div>
                            <div className="min-w-0">
                              <p className="font-medium truncate">{stageLabels[entry.stage] || entry.stage}</p>
                              <p className="text-sm text-muted-foreground">
                                {formatDate(entry.timestamp)} • {entry.runtime_seconds?.toFixed(1)}s • Commit: {entry.git_sha}
                              </p>
                            </div>
                          </div>

                          {/* Record counts */}
                          <div className="flex items-center gap-6 text-sm text-muted-foreground font-mono hidden md:flex">
                            {entry.counts.negotiated_rate_entries_processed !== undefined && (
                              <span>In: {entry.counts.negotiated_rate_entries_processed.toLocaleString()}</span>
                            )}
                            {entry.counts.output_records_generated !== undefined && (
                              <span>Out: {entry.counts.output_records_generated.toLocaleString()}</span>
                            )}
                            {entry.counts.input_c4_rows !== undefined && (
                              <span>In: {entry.counts.input_c4_rows.toLocaleString()}</span>
                            )}
                            {entry.counts.output_rows !== undefined && (
                              <span>Out: {entry.counts.output_rows.toLocaleString()}</span>
                            )}
                            {entry.counts.c5_rows !== undefined && (
                              <span>In: {entry.counts.c5_rows.toLocaleString()}</span>
                            )}
                            {entry.counts.c6_rows !== undefined && (
                              <span>Out: {entry.counts.c6_rows.toLocaleString()}</span>
                            )}
                          </div>

                          {/* Status badge */}
                          <Badge
                            variant={
                              status === "completed"
                                ? "default"
                                : status === "running"
                                ? "secondary"
                                : status === "pending"
                                ? "outline"
                                : "destructive"
                            }
                            className="text-xs"
                          >
                            {status === "completed" && <CheckCircle className="h-3 w-3 mr-1" />}
                            {status === "running" && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                            {status === "pending" && <Clock className="h-3 w-3 mr-1" />}
                            {status === "failed" && <XCircle className="h-3 w-3 mr-1" />}
                            {status.charAt(0).toUpperCase() + status.slice(1)}
                          </Badge>

                          {/* Expand chevron */}
                          <div className="flex-shrink-0 w-8 text-right">
                            {isExpanded ? (
                              <ChevronUp className="h-5 w-5 text-muted-foreground mx-auto" />
                            ) : (
                              <ChevronDown className="h-5 w-5 text-muted-foreground mx-auto" />
                            )}
                          </div>
                        </div>
                      </CollapsibleTrigger>

                      <CollapsibleContent className="p-4 border-t bg-muted/30">
                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                          {Object.entries(entry.counts).map(([key, value]) => (
                            typeof value === "number" && (
                              <div key={key} className="p-3 bg-background rounded-lg">
                                <p className="text-xs text-muted-foreground uppercase tracking-wider">
                                  {key.replace(/_/g, " ")}
                                </p>
                                <p className="text-lg font-bold tabular-nums">{value.toLocaleString()}</p>
                              </div>
                            )
                          ))}
                        </div>

                        {/* Sources */}
                        {(entry as any).sources && (entry as any).sources.length > 0 && (
                          <div className="mt-4">
                            <p className="text-sm font-medium text-muted-foreground mb-2">Sources</p>
                            <ul className="space-y-1 text-sm">
                              {(entry as any).sources.map((source: any, i: number) => (
                                <li key={i} className="flex items-center gap-2 text-muted-foreground font-mono text-xs">
                                  <FileText className="h-3 w-3" />
                                  <span className="truncate">{source.path || source.archive_member || source.member}</span>
                                  {source.size && (
                                    <span className="text-xs text-muted-foreground/50">
                                      ({(source.size / 1024 / 1024).toFixed(1)} MB)
                                    </span>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </CollapsibleContent>
                    </Collapsible>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>

        {/* Legend */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Legend</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-green-500" />
                <span>Completed</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
                <span>Running</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full border border-dashed border-muted-foreground/50" />
                <span>Pending</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500" />
                <span>Failed</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </DashboardLayout>
  );
}