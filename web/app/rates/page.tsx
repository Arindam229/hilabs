"use client";

import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  X,
  Download,
  Columns,
} from "lucide-react";
import {
  useTable,
  flexRender,
  createColumnHelper,
  tableFeatures,
  columnFilteringFeature,
  globalFilteringFeature,
  rowSortingFeature,
  rowPaginationFeature,
  columnVisibilityFeature,
  createFilteredRowModel,
  createCoreRowModel,
  createSortedRowModel,
  createPaginatedRowModel,
  filterFn_includesString,
  sortFn_alphanumeric,
  type SortingState,
  type ColumnFiltersState,
  type PaginationState,
  type ColumnDef,
  type TableFeatures,
  type ColumnVisibilityState,
} from "@tanstack/react-table";
import {
  table_getCoreRowModel as getCoreRowModel,
  table_getSortedRowModel as getSortedRowModel,
  table_getFilteredRowModel as getFilteredRowModel,
  table_getPaginatedRowModel as getPaginationRowModel,
} from "@tanstack/table-core/static-functions";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
} from "@/components/ui/table";
import {
  ScrollArea,
} from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { RateRecord } from "@/lib/types";

const features = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  rowSortingFeature,
  rowPaginationFeature,
  columnVisibilityFeature,
  coreRowModel: createCoreRowModel(),
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  filterFns: {
    includesString: filterFn_includesString,
  },
  sortFns: {
    alphanumeric: sortFn_alphanumeric,
  },
});

const columnHelper = createColumnHelper<typeof features, RateRecord>();

const columns = [
  // 1. NPI
  columnHelper.accessor("npi", {
    id: "NPI",
    header: "NPI",
    cell: (info) => <span className="font-mono text-sm font-medium">{String(info.getValue())}</span>,
    filterFn: "includesString",
  }),
  // 2. TIN
  columnHelper.accessor("tin", {
    id: "TIN",
    header: "TIN",
    cell: (info) => <span className="font-mono text-sm">{String(info.getValue())}</span>,
    filterFn: "includesString",
  }),
  // 3. Address
  columnHelper.accessor("address", {
    id: "Address",
    header: "Address",
    cell: (info) => (
      <span className="text-sm max-w-[220px] truncate block" title={String(info.getValue())}>
        {String(info.getValue())}
      </span>
    ),
  }),
  // 4. Billing Code
  columnHelper.accessor("billing_code", {
    id: "Billing Code",
    header: "Billing Code",
    cell: (info) => (
      <Badge variant="outline" className="text-xs font-mono">
        {String(info.getValue())}
      </Badge>
    ),
    filterFn: "includesString",
  }),
  // 5. Specialty
  columnHelper.accessor("specialty", {
    id: "Specialty",
    header: "Specialty",
    cell: (info) => (
      <span className="text-sm max-w-[200px] truncate block" title={String(info.getValue())}>
        {String(info.getValue())}
      </span>
    ),
    filterFn: "includesString",
  }),
  // 6. Rate
  columnHelper.accessor("rate", {
    id: "Rate",
    header: "Rate",
    cell: (info) => (
      <span className="font-mono tabular-nums text-sm font-semibold">${Number(info.getValue()).toFixed(2)}</span>
    ),
  }),
  // 7. Address_Status
  columnHelper.accessor((row) => row.Address_Status || row.address_status, {
    id: "Address_Status",
    header: "Address_Status",
    cell: (info) => {
      const status = String(info.getValue() || "").toLowerCase();
      const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
        corroborated: "default",
        single_source: "secondary",
        conflicting: "destructive",
        unresolved: "outline",
      };
      return (
        <Badge variant={variants[status] || "outline"} className="text-xs">
          {String(info.getValue() || "")}
        </Badge>
      );
    },
    filterFn: "includesString",
  }),
  // 8. Address_Source
  columnHelper.accessor((row) => row.Address_Source || row.address_source, {
    id: "Address_Source",
    header: "Address_Source",
    cell: (info) => (
      <span className="text-xs font-mono text-muted-foreground max-w-[160px] truncate block" title={String(info.getValue() || "")}>
        {String(info.getValue() || "")}
      </span>
    ),
  }),
  // 9. Address_Confidence
  columnHelper.accessor((row) => row.Address_Confidence || row.address_confidence, {
    id: "Address_Confidence",
    header: "Address_Confidence",
    cell: (info) => (
      <Badge variant="outline" className="text-xs font-mono">
        {String(info.getValue() || "")}
      </Badge>
    ),
  }),
  // 10. Address_Source_Count
  columnHelper.accessor((row) => row.Address_Source_Count ?? row.address_source_count, {
    id: "Address_Source_Count",
    header: "Address_Source_Count",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() ?? "")}</span>,
  }),
  // 11. Address_Score
  columnHelper.accessor((row) => row.Address_Score ?? row.address_score, {
    id: "Address_Score",
    header: "Address_Score",
    cell: (info) => <span className="font-mono text-xs font-semibold">{String(info.getValue() ?? "")}</span>,
  }),
  // 12. Address_Verification_Status
  columnHelper.accessor((row) => row.Address_Verification_Status || row.address_verification_status, {
    id: "Address_Verification_Status",
    header: "Address_Verification_Status",
    cell: (info) => (
      <Badge variant="secondary" className="text-xs font-mono">
        {String(info.getValue() || "")}
      </Badge>
    ),
  }),
  // 13. Address_Evidence_Tier
  columnHelper.accessor((row) => row.Address_Evidence_Tier || row.address_evidence_tier, {
    id: "Address_Evidence_Tier",
    header: "Address_Evidence_Tier",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 14. Taxonomy_Code
  columnHelper.accessor((row) => row.Taxonomy_Code || row.taxonomy_code, {
    id: "Taxonomy_Code",
    header: "Taxonomy_Code",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 15. Specialty_Source
  columnHelper.accessor((row) => row.Specialty_Source || row.specialty_source, {
    id: "Specialty_Source",
    header: "Specialty_Source",
    cell: (info) => (
      <Badge variant="outline" className="text-xs">
        {String(info.getValue() || "")}
      </Badge>
    ),
    filterFn: "includesString",
  }),
  // 16. Negotiated_Type
  columnHelper.accessor((row) => row.Negotiated_Type || row.negotiated_type, {
    id: "Negotiated_Type",
    header: "Negotiated_Type",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 17. Billing_Class
  columnHelper.accessor((row) => row.Billing_Class || row.billing_class, {
    id: "Billing_Class",
    header: "Billing_Class",
    cell: (info) => <span className="text-xs capitalize">{String(info.getValue() || "")}</span>,
  }),
  // 18. Address_Candidate_Count
  columnHelper.accessor((row) => row.Address_Candidate_Count ?? row.address_candidate_count, {
    id: "Address_Candidate_Count",
    header: "Address_Candidate_Count",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() ?? "")}</span>,
  }),
  // 19. Address_Selection_Status
  columnHelper.accessor((row) => row.Address_Selection_Status || row.address_selection_status, {
    id: "Address_Selection_Status",
    header: "Address_Selection_Status",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 20. Address_Selection_Reason
  columnHelper.accessor((row) => row.Address_Selection_Reason || row.address_selection_reason, {
    id: "Address_Selection_Reason",
    header: "Address_Selection_Reason",
    cell: (info) => (
      <span className="text-xs text-muted-foreground max-w-[200px] truncate block" title={String(info.getValue() || "")}>
        {String(info.getValue() || "")}
      </span>
    ),
  }),
  // 21. Specialty_Status
  columnHelper.accessor((row) => row.Specialty_Status || row.specialty_status, {
    id: "Specialty_Status",
    header: "Specialty_Status",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 22. Geocode_Status
  columnHelper.accessor((row) => row.Geocode_Status || row.geocode_status, {
    id: "Geocode_Status",
    header: "Geocode_Status",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 23. Latitude
  columnHelper.accessor((row) => row.Latitude ?? row.latitude, {
    id: "Latitude",
    header: "Latitude",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() ?? "")}</span>,
  }),
  // 24. Longitude
  columnHelper.accessor((row) => row.Longitude ?? row.longitude, {
    id: "Longitude",
    header: "Longitude",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() ?? "")}</span>,
  }),
  // 25. Nearest_TIN_Site_Distance_Km
  columnHelper.accessor((row) => row.Nearest_TIN_Site_Distance_Km ?? row.nearest_tin_site_distance_km, {
    id: "Nearest_TIN_Site_Distance_Km",
    header: "Nearest_TIN_Site_Distance_Km",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() ?? "")}</span>,
  }),
  // 26. Geo_Score
  columnHelper.accessor((row) => row.Geo_Score ?? row.geo_score, {
    id: "Geo_Score",
    header: "Geo_Score",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() ?? "")}</span>,
  }),
  // 27. Geo_Anomaly_Flag
  columnHelper.accessor((row) => row.Geo_Anomaly_Flag || row.geo_anomaly_flag, {
    id: "Geo_Anomaly_Flag",
    header: "Geo_Anomaly_Flag",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 28. TIN_Modal_ZIP3
  columnHelper.accessor((row) => row.TIN_Modal_ZIP3 || row.tin_modal_zip3, {
    id: "TIN_Modal_ZIP3",
    header: "TIN_Modal_ZIP3",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 29. TIN_Support_Score
  columnHelper.accessor((row) => row.TIN_Support_Score ?? row.tin_support_score, {
    id: "TIN_Support_Score",
    header: "TIN_Support_Score",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() ?? "")}</span>,
  }),
  // 30. TIN_Address_Link_Status
  columnHelper.accessor((row) => row.TIN_Address_Link_Status || row.tin_address_link_status, {
    id: "TIN_Address_Link_Status",
    header: "TIN_Address_Link_Status",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 31. Reassignment_Status
  columnHelper.accessor((row) => row.Reassignment_Status || row.reassignment_status, {
    id: "Reassignment_Status",
    header: "Reassignment_Status",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 32. Group_PAC_ID
  columnHelper.accessor((row) => row.Group_PAC_ID || row.group_pac_id, {
    id: "Group_PAC_ID",
    header: "Group_PAC_ID",
    cell: (info) => <span className="font-mono text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 33. Reassignment_Group_Name
  columnHelper.accessor((row) => row.Reassignment_Group_Name || row.reassignment_group_name, {
    id: "Reassignment_Group_Name",
    header: "Reassignment_Group_Name",
    cell: (info) => (
      <span className="text-xs max-w-[180px] truncate block" title={String(info.getValue() || "")}>
        {String(info.getValue() || "")}
      </span>
    ),
  }),
  // 34. Reassignment_Name_Match
  columnHelper.accessor((row) => row.Reassignment_Name_Match || row.reassignment_name_match, {
    id: "Reassignment_Name_Match",
    header: "Reassignment_Name_Match",
    cell: (info) => <span className="text-xs">{String(info.getValue() || "")}</span>,
  }),
  // 35. HN_Hidden_Reason
  columnHelper.accessor((row) => row.HN_Hidden_Reason || row.hn_hidden_reason, {
    id: "HN_Hidden_Reason",
    header: "HN_Hidden_Reason",
    cell: (info) => <span className="text-xs text-muted-foreground">{String(info.getValue() || "")}</span>,
  }),
  // 36. PECOS_Enrollment
  columnHelper.accessor((row) => row.PECOS_Enrollment || row.pecos_enrollment, {
    id: "PECOS_Enrollment",
    header: "PECOS_Enrollment",
    cell: (info) => (
      <Badge variant="outline" className="text-xs font-mono">
        {String(info.getValue() || "")}
      </Badge>
    ),
  }),
];

export default function RatesPage() {
  const [data, setData] = useState<RateRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterOptions, setFilterOptions] = useState<{
    billingCodes: string[];
    specialties: string[];
    addressStatuses: Array<{ value: string; label: string }>;
  }>({
    billingCodes: [],
    specialties: [],
    addressStatuses: [],
  });
  const [globalFilter, setGlobalFilter] = useState("");
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([
    { id: "address_status", value: "corroborated" },
  ]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibilityState>({});
  const [showFilters, setShowFilters] = useState(false);

  // Initialize column visibility
  useEffect(() => {
    const initialVisibility: Record<string, boolean> = {};
    columns.forEach((col) => {
      if (col.id) {
        initialVisibility[col.id] = true;
      }
    });
    setColumnVisibility(initialVisibility);
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: String(pagination.pageIndex + 1),
        pageSize: String(pagination.pageSize),
      });
      if (globalFilter) params.set("search", globalFilter);
      columnFilters.forEach((filter) => {
        if (filter.value) params.set(filter.id, String(filter.value));
      });

      const response = await fetch(`/api/rates?${params.toString()}`);
      if (!response.ok) throw new Error("Failed to fetch rates");
      const json = await response.json();
      setData(json.records);
      setTotal(json.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetch("/api/rates/options")
      .then((res) => res.json())
      .then((opts) => setFilterOptions(opts))
      .catch((err) => console.error("Failed to load rate filter options:", err));
  }, []);

  useEffect(() => {
    fetchData();
  }, [globalFilter, columnFilters, sorting, pagination]);

  const table = useTable<typeof features, RateRecord>({
    features,
    data,
    columns: columns as ColumnDef<typeof features, RateRecord, unknown>[],
    state: {
      sorting,
      columnFilters,
      globalFilter,
      pagination,
      columnVisibility,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    onColumnVisibilityChange: setColumnVisibility,
    manualPagination: true,
    manualFiltering: true,
    manualSorting: true,
    pageCount: Math.ceil(total / pagination.pageSize),
  });

  const handleGlobalFilterChange = (value: string) => {
    setGlobalFilter(value);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  const handleColumnFilterChange = (columnId: string, value: unknown) => {
    setColumnFilters((prev) =>
      prev.filter((f) => f.id !== columnId).concat({ id: columnId, value })
    );
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  const clearFilters = () => {
    setGlobalFilter("");
    setColumnFilters([]);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  const handleExportCSV = () => {
    if (data.length === 0) return;
    const headers = [
      "NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate",
      "Address_Status", "Address_Source", "Address_Confidence",
      "Address_Source_Count", "Address_Score", "Address_Verification_Status",
      "Address_Evidence_Tier", "Taxonomy_Code", "Specialty_Source",
      "Negotiated_Type", "Billing_Class", "Address_Candidate_Count",
      "Address_Selection_Status", "Address_Selection_Reason", "Specialty_Status",
      "Geocode_Status", "Latitude", "Longitude", "Nearest_TIN_Site_Distance_Km",
      "Geo_Score", "Geo_Anomaly_Flag", "TIN_Modal_ZIP3", "TIN_Support_Score",
      "TIN_Address_Link_Status", "Reassignment_Status", "Group_PAC_ID",
      "Reassignment_Group_Name", "Reassignment_Name_Match",
      "HN_Hidden_Reason", "PECOS_Enrollment"
    ];
    const rows = data.map((r) => [
      `"${r.npi || r.NPI || ""}"`,
      `"${r.tin || r.TIN || ""}"`,
      `"${(r.address || r.Address || "").replace(/"/g, '""')}"`,
      `"${r.billing_code || r["Billing Code"] || ""}"`,
      `"${(r.specialty || r.Specialty || "").replace(/"/g, '""')}"`,
      r.rate ?? r.Rate ?? 0,
      `"${r.Address_Status || r.address_status || ""}"`,
      `"${r.Address_Source || r.address_source || ""}"`,
      `"${r.Address_Confidence || r.address_confidence || ""}"`,
      r.Address_Source_Count ?? r.address_source_count ?? 0,
      r.Address_Score ?? r.address_score ?? 0,
      `"${r.Address_Verification_Status || r.address_verification_status || ""}"`,
      `"${r.Address_Evidence_Tier || r.address_evidence_tier || ""}"`,
      `"${r.Taxonomy_Code || r.taxonomy_code || ""}"`,
      `"${r.Specialty_Source || r.specialty_source || ""}"`,
      `"${r.Negotiated_Type || r.negotiated_type || ""}"`,
      `"${r.Billing_Class || r.billing_class || ""}"`,
      r.Address_Candidate_Count ?? r.address_candidate_count ?? 0,
      `"${r.Address_Selection_Status || r.address_selection_status || ""}"`,
      `"${(r.Address_Selection_Reason || r.address_selection_reason || "").replace(/"/g, '""')}"`,
      `"${r.Specialty_Status || r.specialty_status || ""}"`,
      `"${r.Geocode_Status || r.geocode_status || ""}"`,
      `"${r.Latitude ?? r.latitude ?? ""}"`,
      `"${r.Longitude ?? r.longitude ?? ""}"`,
      `"${r.Nearest_TIN_Site_Distance_Km ?? r.nearest_tin_site_distance_km ?? ""}"`,
      `"${r.Geo_Score ?? r.geo_score ?? ""}"`,
      `"${r.Geo_Anomaly_Flag || r.geo_anomaly_flag || ""}"`,
      `"${r.TIN_Modal_ZIP3 || r.tin_modal_zip3 || ""}"`,
      `"${r.TIN_Support_Score ?? r.tin_support_score ?? ""}"`,
      `"${r.TIN_Address_Link_Status || r.tin_address_link_status || ""}"`,
      `"${r.Reassignment_Status || r.reassignment_status || ""}"`,
      `"${r.Group_PAC_ID || r.group_pac_id || ""}"`,
      `"${(r.Reassignment_Group_Name || r.reassignment_group_name || "").replace(/"/g, '""')}"`,
      `"${r.Reassignment_Name_Match || r.reassignment_name_match || ""}"`,
      `"${r.HN_Hidden_Reason || r.hn_hidden_reason || ""}"`,
      `"${r.PECOS_Enrollment || r.pecos_enrollment || ""}"`,
    ]);
    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `hilabs_rates_export_${new Date().toISOString().slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const hasActiveFilters =
    globalFilter || columnFilters.some((f) => f.value !== undefined && f.value !== "");

  const visibleColumnCount = Object.values(columnVisibility).filter((v) => v !== false).length;

  return (
    <DashboardLayout
      title="Rates Explorer"
      showSearch={true}
      onSearch={handleGlobalFilterChange}
      searchPlaceholder="Search NPI, TIN, Address..."
    >
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="space-y-6"
      >
        {/* Toolbar */}
        <Card className="overflow-visible">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-3 w-full">
              {/* Global Search */}
              <div className="relative flex-1 min-w-[250px] max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search NPI, TIN, Address, Billing Code..."
                  value={globalFilter}
                  onChange={(e) => handleGlobalFilterChange(e.target.value)}
                  className="pl-9 h-9"
                  aria-label="Global search"
                />
              </div>

              {/* Column Visibility Selector (collapsible) */}
              <details className="relative">
                <summary className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium shadow-xs hover:bg-accent hover:text-accent-foreground cursor-pointer list-none select-none">
                  <Columns className="h-4 w-4" />
                  <span>Columns ({visibleColumnCount}/{columns.length})</span>
                </summary>
                <div className="absolute z-50 mt-2 w-80 max-h-96 overflow-y-auto rounded-md border border-border bg-card p-3 shadow-lg">
                  <div className="flex items-center justify-between pb-2 mb-1 border-b border-border">
                    <span className="text-sm font-semibold">Display Columns ({columns.length})</span>
                    <div className="flex items-center gap-1.5 text-xs">
                      <button
                        type="button"
                        onClick={() => {
                          const all: Record<string, boolean> = {};
                          columns.forEach((c) => { if (c.id) all[c.id] = true; });
                          setColumnVisibility(all);
                        }}
                        className="text-primary hover:underline font-medium cursor-pointer"
                      >
                        All
                      </button>
                      <span>·</span>
                      <button
                        type="button"
                        onClick={() => {
                          const core: Record<string, boolean> = {};
                          columns.forEach((c, idx) => { if (c.id) core[c.id] = idx < 6; });
                          setColumnVisibility(core);
                        }}
                        className="text-muted-foreground hover:underline font-medium cursor-pointer"
                      >
                        Core 6
                      </button>
                    </div>
                  </div>
                  <div className="space-y-0.5">
                    {columns.map((col) => {
                      const colId = col.id;
                      if (!colId) return null;
                      const isChecked = columnVisibility[colId] !== false;
                      return (
                        <label key={colId} className="flex items-center gap-2 px-2 py-1 hover:bg-accent/40 rounded cursor-pointer">
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() =>
                              setColumnVisibility((prev) => ({
                                ...prev,
                                [colId]: !isChecked,
                              }))
                            }
                            className="h-4 w-4 rounded border-border"
                          />
                          <span className="text-xs font-mono flex-1 truncate">{colId}</span>
                        </label>
                      );
                    })}
                  </div>
                  <div className="mt-2 pt-2 border-t border-border">
                    <button
                      onClick={clearFilters}
                      disabled={!hasActiveFilters}
                      className="flex w-full items-center justify-center gap-2 py-1 text-xs text-red-600 disabled:opacity-40 cursor-pointer"
                    >
                      <X className="h-3.5 w-3.5" />
                      Reset All Filters
                    </button>
                  </div>
                </div>
              </details>

              {/* Address Status Filter */}
              <Select
                value={(columnFilters.find((f) => f.id === "address_status")?.value as string) || "all"}
                onValueChange={(value) => handleColumnFilterChange("address_status", value === "all" ? undefined : value)}
              >
                <SelectTrigger className="h-9 w-[180px]">
                  <SelectValue placeholder="Address Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  {(filterOptions.addressStatuses || []).map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Billing Code Filter */}
              <Select
                value={(columnFilters.find((f) => f.id === "billing_code")?.value as string) || "all"}
                onValueChange={(value) => handleColumnFilterChange("billing_code", value === "all" ? undefined : value)}
              >
                <SelectTrigger className="h-9 w-[170px]">
                  <SelectValue placeholder="Billing Code" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Billing Codes</SelectItem>
                  {(filterOptions.billingCodes || []).map((code) => (
                    <SelectItem key={code} value={code}>
                      Code {code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Specialty Filter */}
              <Select
                value={(columnFilters.find((f) => f.id === "specialty")?.value as string) || "all"}
                onValueChange={(value) => handleColumnFilterChange("specialty", value === "all" ? undefined : value)}
              >
                <SelectTrigger className="h-9 w-[220px]">
                  <SelectValue placeholder="Specialty" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Specialties</SelectItem>
                  {(filterOptions.specialties || []).map((spec) => (
                    <SelectItem key={spec} value={spec}>
                      {spec}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <div className="flex-1" />

              {/* Export Button */}
              <Button
                variant="outline"
                className="h-9 gap-2 cursor-pointer select-none"
                disabled={loading || data.length === 0}
                onClick={handleExportCSV}
              >
                <Download className="h-4 w-4" />
                Export CSV
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Results Info */}
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Showing {data.length} of {total.toLocaleString()} records
          </span>
          {hasActiveFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters} className="gap-1">
              <X className="h-3 w-3" />
              Clear filters
            </Button>
          )}
        </div>

        {/* Table */}
        <Card className="overflow-x-auto shadow-sm border">
          <CardContent className="p-0">
            {loading ? (
              <div className="p-8">
                <div className="flex items-center justify-center h-64">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              </div>
            ) : (
              <>
                <ScrollArea className="w-full">
                  <Table>
                    <TableHeader>
                      {table.getHeaderGroups().map((headerGroup) => (
                        <TableRow key={headerGroup.id} className="bg-muted">
                          {headerGroup.headers.map((header) => (
                            <TableHead
                              key={header.id}
                              className={cn(
                                "cursor-pointer select-none",
                                header.column.getCanSort() && "hover:bg-muted"
                              )}
                              onClick={header.column.getToggleSortingHandler()}
                              style={{ display: header.column.getIsVisible() ? "" : "none" }}
                            >
                              <div className="flex items-center gap-1">
                                {flexRender(header.column.columnDef.header, header.getContext())}
                                {header.column.getIsSorted() ? (
                                  header.column.getIsSorted() === "asc" ? (
                                    <ChevronUp className="h-4 w-4" />
                                  ) : (
                                    <ChevronDown className="h-4 w-4" />
                                  )
                                ) : null}
                              </div>
                            </TableHead>
                          ))}
                        </TableRow>
                      ))}
                    </TableHeader>
                    <TableBody>
                      {table.getRowModel().rows.length === 0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={columns.length}
                            className="h-64 text-center text-muted-foreground"
                          >
                            No records found
                          </TableCell>
                        </TableRow>
                      ) : (
                        table.getRowModel().rows.map((row, rowIndex) => (
                          <TableRow
                            key={row.id}
                            className={cn(
                              "data-[state=selected]:bg-muted",
                              rowIndex % 2 === 0 ? "bg-background" : "bg-muted/30"
                            )}
                          >
                            {row.getVisibleCells().map((cell) => (
                              <TableCell
                                key={cell.column.id}
                                style={{ display: cell.column.getIsVisible() ? "" : "none" }}
                              >
                                {flexRender(cell.column.columnDef.cell, cell.getContext())}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </ScrollArea>

                {/* Pagination */}
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 border-t lg:pr-72">
                  <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                    <span>
                      Showing{" "}
                      <strong className="text-foreground font-semibold">
                        {data.length > 0 ? (pagination.pageIndex * pagination.pageSize + 1).toLocaleString() : 0}
                      </strong>
                      –
                      <strong className="text-foreground font-semibold">
                        {Math.min((pagination.pageIndex + 1) * pagination.pageSize, data.length).toLocaleString()}
                      </strong>{" "}
                      of{" "}
                      <strong className="text-foreground font-semibold">{data.length.toLocaleString()}</strong> rates
                    </span>
                    <div className="flex items-center gap-1.5 ml-1">
                      <span className="text-xs">Per page:</span>
                      <Select
                        value={String(pagination.pageSize)}
                        onValueChange={(value) =>
                          setPagination((prev) => ({ ...prev, pageSize: Number(value) }))
                        }
                      >
                        <SelectTrigger className="h-8 text-xs w-[85px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {[10, 25, 50, 100].map((size) => (
                            <SelectItem key={size} value={String(size)}>
                              {size}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => table.setPageIndex(0)}
                      disabled={!table.getCanPreviousPage()}
                      className="h-8 w-8 p-0"
                      title="First page"
                      aria-label="First page"
                    >
                      <ChevronsLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => table.previousPage()}
                      disabled={!table.getCanPreviousPage()}
                      className="h-8 px-2.5 gap-1 text-xs"
                      aria-label="Previous page"
                    >
                      <ChevronLeft className="h-4 w-4" />
                      <span className="hidden sm:inline">Prev</span>
                    </Button>
                    <span className="text-xs font-medium px-3 py-1.5 rounded-md bg-muted/60 text-foreground border border-border/50">
                      Page {pagination.pageIndex + 1} of {table.getPageCount().toLocaleString()}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => table.nextPage()}
                      disabled={!table.getCanNextPage()}
                      className="h-8 px-2.5 gap-1 text-xs"
                      aria-label="Next page"
                    >
                      <span className="hidden sm:inline">Next</span>
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => table.setPageIndex(table.getPageCount() - 1)}
                      disabled={!table.getCanNextPage()}
                      className="h-8 w-8 p-0"
                      title="Last page"
                      aria-label="Last page"
                    >
                      <ChevronsRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </DashboardLayout>
  );
}