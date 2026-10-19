"use client";

import { useEffect, useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  MapPin,
  CheckCircle,
  MinusCircle,
  AlertTriangle,
  HelpCircle,
  Filter,
  X,
  Download,
  Search,
} from "lucide-react";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { AddressStatusData, UnresolvedRecord } from "@/lib/types";
import { C5C6EvidenceCard } from "@/components/dashboard/C5C6EvidenceCard";

const statusConfig = {
  corroborated: {
    label: "Corroborated",
    icon: CheckCircle,
    color: "hsl(var(--status-corroborated))",
    bgColor: "bg-green-500/10",
    textColor: "text-green-500",
    borderColor: "border-green-500/20",
    description: "Verified by multiple sources (NPPES + CMS)",
  },
  single_source: {
    label: "Single Source",
    icon: MinusCircle,
    color: "hsl(var(--status-single))",
    bgColor: "bg-yellow-500/10",
    textColor: "text-yellow-500",
    borderColor: "border-yellow-500/20",
    description: "Found in one source only",
  },
  conflicting: {
    label: "Conflicting",
    icon: AlertTriangle,
    color: "hsl(var(--status-conflicting))",
    bgColor: "bg-red-500/10",
    textColor: "text-red-500",
    borderColor: "border-red-500/20",
    description: "Multiple sources disagree",
  },
  unresolved: {
    label: "Unresolved",
    icon: HelpCircle,
    color: "hsl(var(--status-unresolved))",
    bgColor: "bg-gray-500/10",
    textColor: "text-gray-500",
    borderColor: "border-gray-500/20",
    description: "No address found in any source",
  },
};

export default function AddressPage() {
  const [data, setData] = useState<AddressStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unresolvedSearch, setUnresolvedSearch] = useState("");

  const unresolvedList = useMemo(() => {
    const list = data?.unresolvedRecords || [];
    if (!unresolvedSearch.trim()) return list;
    const q = unresolvedSearch.toLowerCase();
    return list.filter(
      (item) =>
        item.npi.toLowerCase().includes(q) ||
        item.tin.toLowerCase().includes(q) ||
        item.specialty.toLowerCase().includes(q) ||
        item.reason.toLowerCase().includes(q)
    );
  }, [data?.unresolvedRecords, unresolvedSearch]);

  const handleExportUnresolved = () => {
    const list = data?.unresolvedRecords || [];
    if (list.length === 0) return;
    const headers = ["NPI", "TIN", "Specialty", "Evidence Tier", "Reason"];
    const rows = list.map((r) => [
      `"${r.npi}"`,
      `"${r.tin}"`,
      `"${(r.specialty || "").replace(/"/g, '""')}"`,
      `"${r.evidence_tier || ""}"`,
      `"${(r.reason || "").replace(/"/g, '""')}"`,
    ]);
    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `hilabs_unresolved_addresses_${new Date().toISOString().slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const response = await fetch("/api/address");
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
      <DashboardLayout title="Address Coverage">
        <div className="space-y-6" role="status" aria-label="Loading address coverage data">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[...Array(4)].map((_, i) => (
              <Card key={i}>
                <CardContent className="p-6 text-center">
                  <Skeleton className="h-16 w-16 rounded-full mx-auto mb-4" />
                  <Skeleton className="h-4 w-24 mx-auto" />
                  <Skeleton className="h-3 w-32 mx-auto mt-2" />
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Corroboration Tiers</CardTitle>
            </CardHeader>
            <CardContent>
              <Skeleton className="h-64 w-full" />
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout title="Address Coverage">
        <div className="text-center py-12">
          <p className="text-red-500">Error loading data: {error}</p>
        </div>
      </DashboardLayout>
    );
  }

  if (!data) return null;

  const { corroborated, single_source, conflicting, unresolved, total } = data;
  const verifiedTotal = corroborated + single_source;
  const verifiedPct = total > 0 ? Math.round((verifiedTotal / total) * 100) : 0;

  const statusOrder = ["corroborated", "single_source", "conflicting", "unresolved"] as const;

  return (
    <DashboardLayout title="Address Coverage">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="space-y-6"
      >
        {/* Summary Cards */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {statusOrder.map((status, index) => {
            const config = statusConfig[status];
            const count = data[status as keyof AddressStatusData] as number;
            const pct = total > 0 ? Math.round((count / total) * 100) : 0;
            return (
              <motion.div
                key={status}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: index * 0.05 }}
              >
                <Card className={cn("border-2", config.borderColor)}>
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">{config.label}</p>
                        <p className="text-3xl font-bold tabular-nums mt-1">{count.toLocaleString()}</p>
                        <p className="text-sm font-medium mt-1">{pct}% of total</p>
                      </div>
                      <div
                        className={cn(
                          "flex items-center justify-center w-12 h-12 rounded-xl",
                          config.bgColor
                        )}
                      >
                        <config.icon className={cn("h-6 w-6", config.textColor)} />
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground mt-4">{config.description}</p>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>

        {/* Donut Chart & Corroboration Tiers */}
        <div className="grid gap-6 md:grid-cols-2">
          {/* Donut Chart */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <MapPin className="h-4 w-4" />
                Address Status Distribution
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-center">
                <div className="relative w-64 h-64">
                  <div
                    className="w-full h-full rounded-full"
                    style={{
                      background: `conic-gradient(
                        hsl(var(--status-corroborated)) 0deg ${(corroborated / total) * 360}deg,
                        hsl(var(--status-single)) ${(corroborated / total) * 360}deg ${((corroborated + single_source) / total) * 360}deg,
                        hsl(var(--status-conflicting)) ${((corroborated + single_source) / total) * 360}deg ${((corroborated + single_source + conflicting) / total) * 360}deg,
                        hsl(var(--status-unresolved)) ${((corroborated + single_source + conflicting) / total) * 360}deg 360deg
                      )`,
                    }}
                  >
                    <div className="w-[60%] h-[60%] rounded-full bg-background absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center justify-center">
                      <span className="text-3xl font-bold tabular-nums">{verifiedPct}%</span>
                      <span className="text-xs text-muted-foreground">Verified</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Legend */}
              <div className="flex flex-wrap items-center justify-center gap-4 text-sm">
                {statusOrder.map((status) => {
                  const config = statusConfig[status];
                  const count = data[status as keyof AddressStatusData] as number;
                  return (
                    <div key={status} className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded"
                        style={{ backgroundColor: config.color }}
                      />
                      <span>{config.label}: {count.toLocaleString()}</span>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Corroboration Tiers Bar Chart */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <CheckCircle className="h-4 w-4" />
                Corroboration Tiers
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                {(data.tiers && data.tiers.length > 0
                  ? data.tiers
                  : [
                      { label: "Tier 1: NPPES + CMS DAC Corroborated", value: corroborated, color: "hsl(var(--status-corroborated))" },
                      { label: "Tier 2: Single Source Corroborated", value: single_source, color: "hsl(var(--status-single))" },
                      { label: "Conflicting Multiple Addresses", value: conflicting, color: "hsl(var(--status-conflicting))" },
                      { label: "Tier 4: No Match Found (Unresolved)", value: unresolved, color: "hsl(var(--status-unresolved))" },
                    ]
                ).map((tier, index) => {
                  const pct = total > 0 ? (tier.value / total) * 100 : 0;
                  return (
                    <motion.div
                      key={tier.label}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3, delay: index * 0.05 }}
                      className="space-y-1"
                    >
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{tier.label}</span>
                        <span className="font-mono tabular-nums">{tier.value.toLocaleString()} ({pct.toFixed(1)}%)</span>
                      </div>
                      <div className="h-3 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${pct}%`,
                            backgroundColor: tier.color,
                          }}
                        />
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* C5 Heuristic Scoring Matrix & C6 Multi-Source Verification Breakdown */}
        <C5C6EvidenceCard />

        {/* Unresolved List */}
        <Card>
          <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-lg flex items-center gap-2">
                <HelpCircle className="h-4 w-4" />
                Unresolved Addresses
              </CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                Providers without matching address corroboration across NPPES and CMS DAC
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative min-w-[200px] max-w-xs">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="Filter by NPI, TIN, specialty..."
                  value={unresolvedSearch}
                  onChange={(e) => setUnresolvedSearch(e.target.value)}
                  className="h-8 pl-8 text-xs bg-card"
                />
              </div>
              <Badge variant="outline" className="text-xs">
                {unresolvedList.length} of {unresolved}
              </Badge>
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportUnresolved}
                disabled={unresolvedList.length === 0}
                className="gap-1.5 h-8 text-xs cursor-pointer select-none"
              >
                <Download className="h-3.5 w-3.5" />
                Export CSV
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {unresolvedList.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <HelpCircle className="h-10 w-10 mx-auto mb-3 text-muted-foreground/40" />
                <p className="text-sm">
                  {unresolvedSearch ? "No matching unresolved records found for filter." : "All addresses resolved successfully!"}
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>NPI</TableHead>
                      <TableHead>TIN</TableHead>
                      <TableHead>Specialty</TableHead>
                      <TableHead>Tier</TableHead>
                      <TableHead>Resolution Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {unresolvedList.map((item) => (
                      <TableRow key={`${item.npi}-${item.tin}-${item.specialty}`}>
                        <TableCell className="font-mono text-xs">{item.npi}</TableCell>
                        <TableCell className="font-mono text-xs">{item.tin}</TableCell>
                        <TableCell className="text-sm">{item.specialty}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs">
                            {item.evidence_tier}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="text-xs font-normal">
                            {item.reason}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </DashboardLayout>
  );
}