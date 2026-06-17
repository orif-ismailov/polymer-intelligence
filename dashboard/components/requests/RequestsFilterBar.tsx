"use client";

/**
 * RequestsFilterBar — Period / Product / Region / Source selects + "More Filters"
 * + removable active-filter chips + "Clear filters" reset.
 *
 * All filter state is persisted in URL search params via useSearchParams +
 * router.replace (same pattern as FeedFilters from 04-03).
 * No hardcoded hex — token classes only (UI-SPEC §Color).
 */

import { useRouter, useSearchParams } from "next/navigation";
import { X, ChevronDown } from "lucide-react";

const PERIOD_OPTIONS = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "all", label: "All time" },
];

const URGENCY_OPTIONS = [
  { value: "", label: "All urgency" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "new", label: "New" },
  { value: "viewed", label: "Viewed" },
  { value: "in_progress", label: "In Progress" },
  { value: "offer_sent", label: "Offer Sent" },
  { value: "matched", label: "Matched" },
  { value: "closed", label: "Closed" },
  { value: "cancelled", label: "Cancelled" },
];

interface ActiveFilter {
  key: string;
  label: string;
  value: string;
}

function getActiveFilters(
  period: string,
  urgency: string,
  status: string,
  product: string,
): ActiveFilter[] {
  const filters: ActiveFilter[] = [];
  if (period && period !== "all")
    filters.push({
      key: "period",
      label: "Period",
      value: PERIOD_OPTIONS.find((o) => o.value === period)?.label ?? period,
    });
  if (urgency)
    filters.push({
      key: "urgency",
      label: "Urgency",
      value: URGENCY_OPTIONS.find((o) => o.value === urgency)?.label ?? urgency,
    });
  if (status)
    filters.push({
      key: "status",
      label: "Status",
      value: STATUS_OPTIONS.find((o) => o.value === status)?.label ?? status,
    });
  if (product) filters.push({ key: "product", label: "Product", value: product });
  return filters;
}

export function RequestsFilterBar() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const period = searchParams.get("period") ?? "30d";
  const urgency = searchParams.get("urgency") ?? "";
  const status = searchParams.get("status") ?? "";
  const product = searchParams.get("product") ?? "";

  function setParam(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    // Reset to page 1 when filters change
    params.delete("id");
    router.replace(`?${params.toString()}`);
  }

  function removeFilter(key: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.delete(key);
    params.delete("id");
    router.replace(`?${params.toString()}`);
  }

  function clearFilters() {
    router.replace("?");
  }

  const activeFilters = getActiveFilters(period, urgency, status, product);

  return (
    <div className="flex flex-col gap-3">
      {/* Filter selects row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Period */}
        <div className="relative">
          <label htmlFor="filter-period" className="sr-only">
            Period
          </label>
          <select
            id="filter-period"
            value={period}
            onChange={(e) => setParam("period", e.target.value)}
            className="h-8 rounded-lg border border-border bg-background-secondary px-2.5 pr-8 text-sm text-foreground appearance-none cursor-pointer hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {PERIOD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-foreground-muted"
            aria-hidden="true"
          />
        </div>

        {/* Urgency */}
        <div className="relative">
          <label htmlFor="filter-urgency" className="sr-only">
            Urgency
          </label>
          <select
            id="filter-urgency"
            value={urgency}
            onChange={(e) => setParam("urgency", e.target.value)}
            className="h-8 rounded-lg border border-border bg-background-secondary px-2.5 pr-8 text-sm text-foreground appearance-none cursor-pointer hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {URGENCY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-foreground-muted"
            aria-hidden="true"
          />
        </div>

        {/* Status */}
        <div className="relative">
          <label htmlFor="filter-status" className="sr-only">
            Status
          </label>
          <select
            id="filter-status"
            value={status}
            onChange={(e) => setParam("status", e.target.value)}
            className="h-8 rounded-lg border border-border bg-background-secondary px-2.5 pr-8 text-sm text-foreground appearance-none cursor-pointer hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-foreground-muted"
            aria-hidden="true"
          />
        </div>

        {/* More Filters placeholder button */}
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background-secondary px-3 text-sm text-foreground-muted hover:bg-background-tertiary hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          More Filters
          <ChevronDown size={14} aria-hidden="true" />
        </button>

        {/* Clear filters — only visible when active filters exist */}
        {activeFilters.length > 0 && (
          <button
            type="button"
            onClick={clearFilters}
            className="text-sm text-accent hover:underline transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Active filter chips */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {activeFilters.map((f) => (
            <span
              key={f.key}
              className="inline-flex items-center gap-1 rounded-full bg-background-tertiary px-2.5 py-0.5 text-xs font-semibold text-foreground"
            >
              <span className="text-foreground-muted">{f.label}:</span>
              {f.value}
              <button
                type="button"
                onClick={() => removeFilter(f.key)}
                className="ml-0.5 rounded-full text-foreground-muted hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                aria-label={`Remove ${f.label} filter`}
              >
                <X size={10} aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
