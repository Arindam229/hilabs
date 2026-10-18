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
  columnHelper.accessor("npi", {
    header: "NPI",
    cell: (info) => <span className="font-mono text-sm">{info.getValue()}</span>,
    filterFn: "includesString",
  }),
  columnHelper.accessor("tin", {
    header: "TIN",
    cell: (info) => <span className="font-mono text-sm">{info.getValue()}</span>,
    filterFn: "includesString",
  }),
  columnHelper.accessor("address", {
    header: "Address",
    cell: (info) => (
      <span className="text-sm max-w-[200px] truncate block" title={info.getValue()}>
        {info.getValue()}
      </span>
    ),
  }),
  columnHelper.accessor("billing_code", {
    header: "Billing Code",
    cell: (info) => (
      <Badge variant="outline" className="text-xs">
        {info.getValue()}
      </Badge>
    ),
    filterFn: "includesString",
  }),
  columnHelper.accessor("specialty", {
    header: "Specialty",
    cell: (info) => <span className="text-sm">{info.getValue()}</span>,
    filterFn: "includesString",
  }),
  columnHelper.accessor("rate", {
    header: "Rate",
    cell: (info) => (
      <span className="font-mono tabular-nums text-sm">${info.getValue()}</span>
    ),
  }),
  columnHelper.accessor("address_status", {
    header: "Address Status",
    cell: (info) => {
      const status = info.getValue();
      const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
        corroborated: "default",
        single_source: "secondary",
        conflicting: "destructive",
        unresolved: "outline",
      };
      return (
        <Badge variant={variants[status] || "outline"} className="text-xs capitalize">
          {status.replace("_", " ")}
        </Badge>
      );
    },
    filterFn: "includesString",
  }),
  columnHelper.accessor("specialty_source", {
    header: "Specialty Source",
    cell: (info) => (
      <Badge variant="outline" className="text-xs">
        {info.getValue()}
      </Badge>
    ),
    filterFn: "includesString",
  }),
];

const statusOptions = [
  { value: "corroborated", label: "Corroborated" },
  { value: "single_source", label: "Single Source" },
  { value: "conflicting", label: "Conflicting" },
  { value: "unresolved", label: "Unresolved" },
];

const billingCodes = ["99213", "99214", "99215", "99203", "99204"];
const specialties = ["Internal Medicine", "Family Practice", "Cardiology", "Dermatology", "Orthopedics"];

export default function RatesPage() {
  const [data, setData] = useState<RateRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [globalFilter, setGlobalFilter] = useState("");
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
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

  const hasActiveFilters =
    globalFilter || columnFilters.some((f) => f.value !== undefined && f.value !== "");

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
        <Card>
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

              {/* Column Filters (collapsible) */}
              <details className="relative">
                <summary className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium shadow-xs hover:bg-accent hover:text-accent-foreground cursor-pointer list-none">
                  <Filter className="h-4 w-4" />
                  <span>Filters</span>
                  {hasActiveFilters && (
                    <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
                  )}
                </summary>
                <div className="absolute z-50 mt-2 w-80 rounded-md border border-border bg-card p-2 shadow-md">
                  <div className="px-2 py-1.5 text-sm font-semibold">Column Filters</div>
                  <div className="my-1 h-px bg-border" />
                  {columns.map((col) => {
                    if (!("accessorFn" in col) || !col.id) return null;
                    const colId = col.id;
                    return (
                      <label key={colId} className="flex items-center gap-2 px-2 py-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={columnVisibility[colId]}
                          onChange={() =>
                            setColumnVisibility((prev) => ({
                              ...prev,
                              [colId]: !prev[colId],
                            }))
                          }
                          className="h-4 w-4 rounded border-border"
                        />
                        <span className="text-sm flex-1 capitalize">{colId.replace("_", " ")}</span>
                      </label>
                    );
                  })}
                  <div className="my-1 h-px bg-border" />
                  <button
                    onClick={clearFilters}
                    disabled={!hasActiveFilters}
                    className="flex w-full items-center gap-2 px-2 py-1.5 text-sm text-red-600 disabled:opacity-50"
                  >
                    <X className="h-4 w-4" />
                    Clear All Filters
                  </button>
                </div>
              </details>

              {/* Address Status Filter */}
              <Select
                value={columnFilters.find((f) => f.id === "address_status")?.value as string || ""}
                onValueChange={(value) => handleColumnFilterChange("address_status", value || undefined)}
              >
                <SelectTrigger className="h-9 w-[180px]">
                  <SelectValue placeholder="Address Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All</SelectItem>
                  {statusOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Billing Code Filter */}
              <Select
                value={columnFilters.find((f) => f.id === "billing_code")?.value as string || ""}
                onValueChange={(value) => handleColumnFilterChange("billing_code", value || undefined)}
              >
                <SelectTrigger className="h-9 w-[150px]">
                  <SelectValue placeholder="Billing Code" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All</SelectItem>
                  {billingCodes.map((code) => (
                    <SelectItem key={code} value={code}>
                      {code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Specialty Filter */}
              <Select
                value={columnFilters.find((f) => f.id === "specialty")?.value as string || ""}
                onValueChange={(value) => handleColumnFilterChange("specialty", value || undefined)}
              >
                <SelectTrigger className="h-9 w-[200px]">
                  <SelectValue placeholder="Specialty" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All</SelectItem>
                  {specialties.map((spec) => (
                    <SelectItem key={spec} value={spec}>
                      {spec}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <div className="flex-1" />

              {/* Export Button */}
              <Button variant="outline" className="h-9 gap-2" disabled={loading}>
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
                <div className="flex items-center justify-between p-4 border-t">
                  <div className="flex items-center gap-2">
                    <Select
                      value={String(pagination.pageSize)}
                      onValueChange={(value) =>
                        setPagination((prev) => ({ ...prev, pageSize: Number(value) }))
                      }
                    >
                      <SelectTrigger className="h-8 text-sm w-[100px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[10, 25, 50, 100].map((size) => (
                          <SelectItem key={size} value={String(size)}>
                            {size} per page
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => table.previousPage()}
                      disabled={!table.getCanPreviousPage()}
                      aria-label="Previous page"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      Page {pagination.pageIndex + 1} of {table.getPageCount()}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => table.nextPage()}
                      disabled={!table.getCanNextPage()}
                      aria-label="Next page"
                    >
                      <ChevronRight className="h-4 w-4" />
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