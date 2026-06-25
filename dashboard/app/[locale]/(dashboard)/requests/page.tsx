/**
 * Purchase Requests page — flagship master-detail screen (REQ-purchase-requests).
 *
 * "use client" required so Lucide icon components can be passed as props to KpiCard
 * (functions cannot be passed from Server Components to Client Components in Next.js).
 *
 * Header: title + subtitle, Search input, "Export CSV" button, Settings icon, "● Live Data".
 * KPIs: Total Requests, Total Volume, Avg Target Price, Hot Requests, Sources, Updated.
 * FilterBar: period / urgency / status selects + removable chips.
 * Table: 10-row paginated TanStack Table with sortable columns.
 * Detail panel: mounts when ?id= param is set (keyed off URL).
 *
 * UI-SPEC §Purchase Requests / Export button behavior (CSV).
 * No hardcoded hex — token classes only.
 */

"use client";

import { Suspense } from "react";
import {
  FileText,
  Download,
  Flame,
  Database,
  Clock,
  BarChart2,
  Settings,
} from "lucide-react";

import { KpiCard } from "@/components/shared/KpiCard";
import { RequestsFilterBar } from "@/components/requests/RequestsFilterBar";
import { RequestsTable } from "@/components/requests/RequestsTable";
import { RequestDetailPanel } from "@/components/requests/RequestDetailPanel";
import { ExportCsvButton } from "@/components/requests/ExportCsvButton";

// Spinner fallback for Suspense boundaries
function TableLoadingFallback() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      <span className="ml-3 text-sm text-foreground-muted">Loading…</span>
    </div>
  );
}

export default function RequestsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            Purchase Requests
          </h1>
          <p className="mt-1 text-sm text-foreground-muted">
            Real-time buyer requests collected from exchanges, websites and
            channels
          </p>
        </div>

        {/* Header action buttons */}
        <div className="flex items-center gap-3">
          {/* Search input */}
          <div className="relative hidden sm:block">
            <input
              type="search"
              placeholder="Search requests…"
              aria-label="Search requests"
              className="h-8 w-[280px] rounded-lg border border-border bg-background-secondary pl-3 pr-3 text-sm text-foreground placeholder-foreground-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background hover:bg-background-tertiary"
            />
          </div>

          {/* Export CSV — client component that reads current URL params */}
          <Suspense
            fallback={
              <button
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background-secondary px-3 text-sm text-foreground-muted"
                disabled
              >
                <Download size={14} aria-hidden="true" />
                Export CSV
              </button>
            }
          >
            <ExportCsvButton />
          </Suspense>

          {/* Settings icon button — 44px touch target */}
          <button
            type="button"
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-background-secondary text-foreground-muted hover:bg-background-tertiary hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            aria-label="Table settings"
          >
            <Settings size={16} aria-hidden="true" />
          </button>

          {/* Live Data indicator */}
          <div className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full bg-accent animate-pulse"
              aria-hidden="true"
            />
            <span className="text-xs text-accent font-semibold">Live Data</span>
          </div>
        </div>
      </div>

      {/* KPI cards (6) — UI-SPEC §Purchase Requests KPI cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <KpiCard
          icon={FileText}
          label="Total Requests"
          value="—"
          delta={undefined}
        />
        <KpiCard
          icon={BarChart2}
          label="Total Volume"
          value="—"
          delta={undefined}
        />
        <KpiCard
          icon={Database}
          label="Avg Target Price"
          value="—"
          delta={undefined}
        />
        <KpiCard
          icon={Flame}
          label="Hot Requests"
          value="—"
          delta="urgency=high"
          deltaSentiment="negative"
        />
        <KpiCard
          icon={Database}
          label="Sources"
          value="—"
          delta={undefined}
        />
        <KpiCard
          icon={Clock}
          label="Updated"
          value="—"
          delta={undefined}
        />
      </div>

      {/* Filter bar */}
      <Suspense fallback={null}>
        <RequestsFilterBar />
      </Suspense>

      {/* Requests table */}
      <Suspense fallback={<TableLoadingFallback />}>
        <RequestsTable />
      </Suspense>

      {/* Detail panel — mounts when ?id= is set */}
      <Suspense fallback={null}>
        <RequestDetailPanel />
      </Suspense>
    </div>
  );
}
