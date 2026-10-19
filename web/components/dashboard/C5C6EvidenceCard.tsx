"use client";

import { useState } from "react";
import {
  ShieldCheck,
  Award,
  Layers,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Building2,
  TrendingUp,
  FileCheck2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export const C5_SCORING_WEIGHTS = [
  {
    evidence: "CMS National Provider Directory location",
    points: "+60",
    badgeColor: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30 dark:text-emerald-400 font-mono font-bold",
    trust: "Current, API-served practitioner → location from CMS",
    tier: "CMS Primary",
  },
  {
    evidence: "CMS Doctors & Clinicians (DAC)",
    points: "+50",
    badgeColor: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30 dark:text-emerald-400 font-mono font-bold",
    trust: "Medicare-enrolled clinicians and their practice locations, maintained by CMS separately from NPPES. A practice location here is very likely an active clinic",
    tier: "CMS Primary",
  },
  {
    evidence: "Health Net PPO directory — shown",
    points: "+50",
    badgeColor: "bg-blue-500/10 text-blue-600 border-blue-500/30 dark:text-blue-400 font-mono font-bold",
    trust: "The payer itself lists this NPI at this address in the exact PPO network we price",
    tier: "Payer Direct",
  },
  {
    evidence: "Medicare Part B claims address (2024)",
    points: "+40",
    badgeColor: "bg-indigo-500/10 text-indigo-600 border-indigo-500/30 dark:text-indigo-400 font-mono font-bold",
    trust: "The provider actually billed Medicare from here; two years old, so it supports and never decides",
    tier: "Claims",
  },
  {
    evidence: "Rate-file address",
    points: "+40",
    badgeColor: "bg-slate-500/10 text-slate-500 border-slate-500/30 font-mono",
    trust: "Reserved. TiC in-network files carry no addresses, so this never fires on this dataset",
    tier: "Rate File",
  },
  {
    evidence: "NPPES secondary practice location",
    points: "+30",
    badgeColor: "bg-amber-500/10 text-amber-600 border-amber-500/30 dark:text-amber-400 font-mono font-bold",
    trust: "The primary NPPES address is often a billing or mailing address; the secondary location is often the physical clinic",
    tier: "Registry",
  },
  {
    evidence: "Health Net PPO directory — hidden",
    points: "+20",
    badgeColor: "bg-cyan-500/10 text-cyan-600 border-cyan-500/30 dark:text-cyan-400 font-mono font-bold",
    trust: "A current PPO contract at this address that is hidden from the public site (reason recorded). Attach-only: it never creates a candidate",
    tier: "Payer Hidden",
  },
  {
    evidence: "NPPES primary practice address",
    points: "+10",
    badgeColor: "bg-yellow-500/10 text-yellow-600 border-yellow-500/30 dark:text-yellow-400 font-mono font-bold",
    trust: "Lowest trust: the PS states about 80 % of NPPES addresses are stale or wrong",
    tier: "Registry",
  },
  {
    evidence: "CMS reassignment (exact NPI + group PAC ID, + name match)",
    points: "+15 / +25",
    badgeColor: "bg-teal-500/10 text-teal-600 border-teal-500/30 dark:text-teal-400 font-mono font-bold",
    trust: "Proves which group the clinician bills through",
    tier: "CMS Reassignment",
  },
  {
    evidence: "≥ 2 independent source families agree",
    points: "+20",
    badgeColor: "bg-purple-500/10 text-purple-600 border-purple-500/30 dark:text-purple-400 font-mono font-bold",
    trust: "Corroboration bonus. NPPES primary and secondary count as one family, Health Net shown and hidden as one, and a hidden listing alone never earns it",
    tier: "Bonus",
  },
  {
    evidence: "P.O. box",
    points: "−60",
    badgeColor: "bg-red-500/10 text-red-600 border-red-500/30 dark:text-red-400 font-mono font-bold",
    trust: "A mailing address, not a practice",
    tier: "Penalty",
  },
];

export const C6_VERIFICATION_ROWS = [
  { source: "Health Net PPO directory (shown)", rows: 1675, share: 14.7, badge: "Payer Direct", color: "bg-blue-500" },
  { source: "Medicare claims 2024", rows: 1030, share: 9.0, badge: "Claims", color: "bg-indigo-500" },
  { source: "CMS DAC", rows: 88, share: 0.8, badge: "CMS", color: "bg-emerald-500" },
  { source: "CMS National Provider Directory", rows: 61, share: 0.5, badge: "CMS API", color: "bg-teal-500" },
  { source: "Strong verification subtotal", rows: 2854, share: 25.0, badge: "Strong Subtotal", color: "bg-cyan-500", isStrong: true },
  { source: "Health Net PPO (hidden listing)", rows: 3650, share: 32.0, badge: "Payer Attached", color: "bg-amber-500" },
  { source: "Total with ≥ 2 sources agreeing", rows: 6504, share: 57.1, badge: "Final Corroborated", color: "bg-green-600", isTotal: true },
];

export function C5C6EvidenceCard({ totalRows = 11413 }: { totalRows?: number }) {
  const [activeTab, setActiveTab] = useState<string>("c5-scoring");

  return (
    <Card className="border border-border/80 shadow-xs overflow-hidden">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/20">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
            <div>
              <CardTitle className="text-base font-semibold">
                Address Intelligence &amp; Deliverable Verification (README Methodology)
              </CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                Heuristic domain-knowledge scoring weights (C5) and source-by-source corroboration lift (C6)
              </p>
            </div>
          </div>
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="h-8">
              <TabsTrigger value="c5-scoring" className="text-xs px-3">
                C5 Scoring Weights
              </TabsTrigger>
              <TabsTrigger value="c6-verification" className="text-xs px-3">
                C6 Multi-Source Verification
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </CardHeader>

      <CardContent className="p-4 sm:p-6">
        {activeTab === "c5-scoring" ? (
          <div className="space-y-5">
            {/* Score Thresholds Banner */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">VERIFIED Level</span>
                  <Badge className="bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 font-mono text-[10px]">Score ≥ 60</Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Multi-source agreement required. <strong>No single non-CMS source reaches 60 alone.</strong>
                </p>
              </div>

              <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-amber-700 dark:text-amber-300">PROBABLE Level</span>
                  <Badge className="bg-amber-500/20 text-amber-700 dark:text-amber-300 font-mono text-[10px]">Score 30–59</Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Solid single source (e.g. NPPES + Health Net hidden = 10 + 20 = 30) or secondary practice clinic.
                </p>
              </div>

              <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-rose-700 dark:text-rose-300">LOW Level</span>
                  <Badge className="bg-rose-500/20 text-rose-700 dark:text-rose-300 font-mono text-[10px]">Score &lt; 30</Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  NPPES primary alone (+10) or PO Box penalized (−60); unconfirmed or stale address.
                </p>
              </div>
            </div>

            {/* Heuristic Scoring Table (Exact README Section 7 C5 Table) */}
            <div className="rounded-lg border border-border overflow-hidden">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-muted/40">
                    <TableRow>
                      <TableHead className="w-[300px] text-xs font-semibold">Evidence Source</TableHead>
                      <TableHead className="w-[100px] text-xs font-semibold text-center">Points</TableHead>
                      <TableHead className="text-xs font-semibold">Why this much trust (Domain Rationale)</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {C5_SCORING_WEIGHTS.map((item, idx) => (
                      <TableRow key={idx} className={item.points.startsWith("−") ? "bg-red-500/5" : undefined}>
                        <TableCell className="font-medium text-xs text-foreground">
                          <div className="flex items-center gap-2">
                            <span>{item.evidence}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge variant="outline" className={item.badgeColor}>
                            {item.points}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground leading-relaxed">
                          {item.trust}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-muted/40 border border-border/60 text-xs text-muted-foreground flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-cyan-600 shrink-0" />
                <span>
                  <strong>Building-Level Matching:</strong> Joins payer &amp; claims records when street, city, and ZIP5 match even if suite differs (<code>R-C5-11</code>).
                </span>
              </div>
              <Badge variant="secondary" className="font-mono text-[10px] shrink-0">ZIP5 Canonical Bridge</Badge>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Visual Lift Comparison Banner */}
            <div className="p-4 rounded-xl border border-green-500/30 bg-green-500/5 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Badge className="bg-green-600 text-white font-bold text-xs">11.9x Lift Over Baseline</Badge>
                  <span className="text-xs font-semibold text-foreground">Multi-Source Verification Lift</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  NPPES alone confirmed only <strong>4.8%</strong> of addresses. Cross-referencing Health Net commercial PPO directory and Medicare claims lifts verification to <strong>57.1%</strong>.
                </p>
              </div>
              <div className="flex items-center gap-6 shrink-0">
                <div className="text-center">
                  <div className="text-xl font-bold font-mono text-muted-foreground">4.8%</div>
                  <div className="text-[10px] text-muted-foreground uppercase">NPPES Baseline</div>
                </div>
                <div className="text-gray-400 font-bold">→</div>
                <div className="text-center">
                  <div className="text-xl font-bold font-mono text-cyan-600 dark:text-cyan-400">25.0%</div>
                  <div className="text-[10px] text-cyan-600 dark:text-cyan-400 uppercase font-semibold">Strong Sources</div>
                </div>
                <div className="text-gray-400 font-bold">→</div>
                <div className="text-center">
                  <div className="text-2xl font-black font-mono text-green-600 dark:text-green-400">57.1%</div>
                  <div className="text-[10px] text-green-600 dark:text-green-400 uppercase font-bold">Total Agreed</div>
                </div>
              </div>
            </div>

            {/* C6 Verification Table (Exact README Section 7 C6 Table) */}
            <div className="rounded-lg border border-border overflow-hidden">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-muted/40">
                    <TableRow>
                      <TableHead className="text-xs font-semibold">Verified by</TableHead>
                      <TableHead className="text-xs font-semibold">Category</TableHead>
                      <TableHead className="w-[120px] text-xs font-semibold text-right">Rows</TableHead>
                      <TableHead className="w-[140px] text-xs font-semibold text-right">Share of Final File</TableHead>
                      <TableHead className="w-[180px] text-xs font-semibold">Visual Ratio</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {C6_VERIFICATION_ROWS.map((row, idx) => (
                      <TableRow
                        key={idx}
                        className={
                          row.isTotal
                            ? "bg-green-500/10 font-bold border-t-2 border-green-500/30"
                            : row.isStrong
                            ? "bg-cyan-500/5 font-semibold border-t border-border"
                            : undefined
                        }
                      >
                        <TableCell className="text-xs text-foreground">
                          <div className="flex items-center gap-2">
                            {row.isTotal ? (
                              <CheckCircle2 className="h-4 w-4 text-green-600" />
                            ) : row.isStrong ? (
                              <Award className="h-4 w-4 text-cyan-600" />
                            ) : (
                              <span className="w-2 h-2 rounded-full bg-muted-foreground/50 ml-1" />
                            )}
                            <span className={row.isTotal || row.isStrong ? "font-semibold" : ""}>
                              {row.source}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-[10px]">
                            {row.badge}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {row.rows.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          <span className={row.isTotal ? "text-green-600 dark:text-green-400 font-bold" : ""}>
                            {row.share.toFixed(1)} %
                          </span>
                        </TableCell>
                        <TableCell>
                          <div className="w-full bg-muted/60 rounded-full h-2 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${row.color}`}
                              style={{ width: `${Math.min(100, (row.share / 60) * 100)}%` }}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-muted-foreground">
              <div className="p-3 rounded-lg border border-border bg-card space-y-1">
                <div className="font-semibold text-foreground flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-cyan-600" />
                  Strong Verification (25.0%)
                </div>
                <p className="text-[11px]">
                  Confirmed by live Health Net directory shown listings, 2024 Medicare claims, CMS DAC, or CMS National Provider Directory FHIR API.
                </p>
              </div>
              <div className="p-3 rounded-lg border border-border bg-card space-y-1">
                <div className="font-semibold text-foreground flex items-center gap-1.5">
                  <FileCheck2 className="h-3.5 w-3.5 text-green-600" />
                  Payer PPO Attachment (32.0%)
                </div>
                <p className="text-[11px]">
                  Contracted PPO providers with current Health Net contractual evidence attached, achieving 57.1% total multi-source agreement across 11,413 final rows.
                </p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
