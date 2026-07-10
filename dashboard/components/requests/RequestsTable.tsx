"use client";

/**
 * RequestsTable — TanStack Table (10 rows/page) for Purchase Requests.
 *
 * - useQuery(['requests', filters], ...) fetches from /api/v1/requests with filter params
 * - Row click sets ?id= URL param to open RequestDetailPanel (selected row highlighted)
 * - Sortable columns: Time, Volume, Target Price (ArrowUpDown icon)
 * - Status / Urgency chips via shared components (no hardcoded hex)
 * - Empty state: Inbox icon + copywriting-contract text
 * - Pagination: 10 rows per page, client-side (full list is sorted/paged by TanStack Table)
 *
 * UI-SPEC: /requests table columns, widths, row heights, interaction contract.
 * No hardcoded hex — token classes only (T-04-15).
 */

import { useMemo, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useRouter } from "@/i18n/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowUpDown, ChevronLeft, ChevronRight, Inbox } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { relativeTime } from "@/lib/tz";
import { StatusChip } from "@/components/shared/StatusChip";
import { UrgencyChip } from "@/components/shared/UrgencyChip";

/** RequestListOut from app.schemas.dashboard (04-04). */
export interface RequestListItem {
  id: number;
  number: string;
  status: string;
  product_id: number;
  grade_text: string | null;
  polymer_type: string | null;
  volume: number | string;
  volume_unit: string;
  target_price: number | string | null;
  currency: string;
  urgency: string;
  assigned_to: number | null;
  created_at: string;
  updated_at: string;
}

function buildRequestsUrl(
  status: string,
  urgency: string,
  productId: string,
): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (urgency) params.set("urgency", urgency);
  if (productId) params.set("product_id", productId);
  const qs = params.toString();
  return `/requests${qs ? `?${qs}` : ""}`;
}

const PAGE_SIZE = 10;

const columnHelper = createColumnHelper<RequestListItem>();

export function RequestsTable() {
  const t = useTranslations("requests");
  const router = useRouter();
  const searchParams = useSearchParams();

  const status = searchParams.get("status") ?? "";
  const urgency = searchParams.get("urgency") ?? "";
  const productId = searchParams.get("product") ?? "";
  const selectedId = searchParams.get("id");

  const [sorting, setSorting] = useState<SortingState>([
    { id: "created_at", desc: true },
  ]);
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: PAGE_SIZE });

  const filters = useMemo(
    () => ({ status, urgency, productId }),
    [status, urgency, productId],
  );

  const { data, isLoading, isError, error } = useQuery<RequestListItem[]>({
    queryKey: ["requests", filters],
    queryFn: () =>
      apiFetch<RequestListItem[]>(buildRequestsUrl(status, urgency, productId)),
  });

  const handleRowClick = useCallback(
    (id: number) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("id", String(id));
      router.replace(`?${params.toString()}`);
    },
    [router, searchParams],
  );

  const columns = useMemo(
    () => [
      columnHelper.accessor("created_at", {
        id: "created_at",
        header: ({ column }) => (
          <button
            type="button"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="inline-flex items-center gap-1 text-xs font-semibold text-foreground-muted uppercase tracking-wider hover:text-foreground transition-colors focus-visible:outline-none"
          >
            {t("colTime")}
            <ArrowUpDown size={12} aria-hidden="true" />
          </button>
        ),
        cell: (info) => (
          <time
            dateTime={info.getValue()}
            title={info.getValue()}
            className="text-sm text-foreground-muted whitespace-nowrap"
          >
            {relativeTime(info.getValue())}
          </time>
        ),
        size: 80,
      }),
      columnHelper.accessor("grade_text", {
        id: "product",
        header: () => (
          <span className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
            {t("colProduct")}
          </span>
        ),
        cell: (info) => (
          <span className="text-sm text-foreground">
            {info.getValue() ?? "—"}
          </span>
        ),
        size: 120,
      }),
      columnHelper.accessor("polymer_type", {
        id: "grade_type",
        header: () => (
          <span className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
            {t("colGradeType")}
          </span>
        ),
        cell: (info) => (
          <span className="text-sm text-foreground">
            {info.getValue() ?? "—"}
          </span>
        ),
        size: 100,
      }),
      columnHelper.accessor("volume", {
        id: "volume",
        header: ({ column }) => (
          <button
            type="button"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="inline-flex items-center gap-1 text-xs font-semibold text-foreground-muted uppercase tracking-wider hover:text-foreground transition-colors focus-visible:outline-none"
          >
            {t("colVolume")}
            <ArrowUpDown size={12} aria-hidden="true" />
          </button>
        ),
        cell: (info) => {
          const row = info.row.original;
          return (
            <span className="text-sm font-mono text-foreground">
              {info.getValue() != null
                ? `${info.getValue()} ${row.volume_unit}`
                : "—"}
            </span>
          );
        },
        size: 80,
        sortingFn: "alphanumeric",
      }),
      columnHelper.accessor("target_price", {
        id: "target_price",
        header: ({ column }) => (
          <button
            type="button"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="inline-flex items-center gap-1 text-xs font-semibold text-foreground-muted uppercase tracking-wider hover:text-foreground transition-colors focus-visible:outline-none"
          >
            {t("colTargetPrice")}
            <ArrowUpDown size={12} aria-hidden="true" />
          </button>
        ),
        cell: (info) => {
          const row = info.row.original;
          return (
            <span className="text-sm font-mono text-foreground">
              {info.getValue() != null
                ? `${info.getValue()} ${row.currency}/MT`
                : "—"}
            </span>
          );
        },
        size: 100,
        sortingFn: "alphanumeric",
      }),
      columnHelper.accessor("currency", {
        id: "region",
        header: () => (
          <span className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
            {t("colRegion")}
          </span>
        ),
        cell: () => (
          <span className="text-sm text-foreground">—</span>
        ),
        size: 120,
      }),
      columnHelper.accessor("number", {
        id: "source",
        header: () => (
          <span className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
            {t("colSource")}
          </span>
        ),
        cell: () => (
          <span className="text-sm text-foreground-muted">—</span>
        ),
        size: 140,
      }),
      columnHelper.accessor("urgency", {
        id: "urgency",
        header: () => (
          <span className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
            {t("colUrgency")}
          </span>
        ),
        cell: (info) => {
          const u = info.getValue();
          return u ? (
            <UrgencyChip urgency={u} />
          ) : (
            <span className="text-foreground-subtle">—</span>
          );
        },
        size: 80,
      }),
      columnHelper.accessor("status", {
        id: "status",
        header: () => (
          <span className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
            {t("colStatus")}
          </span>
        ),
        cell: (info) => {
          const s = info.getValue();
          return s ? (
            <StatusChip status={s} />
          ) : (
            <span className="text-foreground-subtle">—</span>
          );
        },
        size: 100,
      }),
    ],
    [t],
  );

  // TanStack Table's useReactTable returns non-memoizable functions, so the React
  // Compiler skips this component — an intrinsic, harmless limitation of the library.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: data ?? [],
    columns,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        <span className="ms-3 text-sm text-foreground-muted">
          {t("loadingRequests")}
        </span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg bg-background-secondary border border-border p-6">
        <p className="text-sm text-urgency-high">
          {t("loadError")}{" "}
          {error instanceof Error ? error.message : t("unknownError")}
        </p>
      </div>
    );
  }

  if (!data?.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <Inbox
          size={32}
          className="text-foreground-muted"
          aria-hidden="true"
        />
        <p className="text-sm font-semibold text-foreground">
          {t("emptyTitle")}
        </p>
        <p className="text-sm text-foreground-muted">
          {t("emptyDescription")}
        </p>
      </div>
    );
  }

  const totalPages = table.getPageCount();

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table
          className="w-full text-sm"
          role="grid"
          aria-label={t("tableAriaLabel")}
        >
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr
                key={headerGroup.id}
                className="border-b border-border bg-background-secondary"
              >
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    style={{ width: header.column.columnDef.size }}
                    className="px-4 py-3 text-start"
                    aria-sort={
                      header.column.getIsSorted() === "asc"
                        ? "ascending"
                        : header.column.getIsSorted() === "desc"
                        ? "descending"
                        : undefined
                    }
                  >
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext(),
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => {
              const isSelected = String(row.original.id) === selectedId;
              return (
                <tr
                  key={row.id}
                  role="row"
                  onClick={() => handleRowClick(row.original.id)}
                  className={`border-b border-border cursor-pointer transition-colors duration-150 ${
                    isSelected
                      ? "bg-background-tertiary"
                      : "bg-background hover:bg-background-secondary"
                  }`}
                  aria-selected={isSelected}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleRowClick(row.original.id);
                    }
                  }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3">
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination controls */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
          className="inline-flex items-center gap-1 rounded-md border border-border bg-background-secondary px-3 py-1.5 text-sm text-foreground disabled:opacity-40 disabled:cursor-not-allowed hover:bg-background-tertiary focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background transition-colors"
          aria-label={t("previousPage")}
        >
          <ChevronLeft size={16} aria-hidden="true" />
          {t("prev")}
        </button>
        <span className="text-xs text-foreground-muted">
          {t("pagination", {
            page: table.getState().pagination.pageIndex + 1,
            totalPages: Math.max(totalPages, 1),
            results: data.length,
          })}
        </span>
        <button
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
          className="inline-flex items-center gap-1 rounded-md border border-border bg-background-secondary px-3 py-1.5 text-sm text-foreground disabled:opacity-40 disabled:cursor-not-allowed hover:bg-background-tertiary focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background transition-colors"
          aria-label={t("nextPage")}
        >
          {t("next")}
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
