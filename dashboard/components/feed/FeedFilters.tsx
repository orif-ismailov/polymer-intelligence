"use client";

/**
 * FeedFilters — period/product/kind/source/urgency selects for the Live Market Feed.
 * Filters are persisted in URL search params (useSearchParams).
 * UI-SPEC §Live Market Feed panel filter bar.
 */

import { useCallback } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";

const PERIOD_OPTIONS = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
];

const KIND_OPTIONS = [
  { value: "", label: "All Kinds" },
  { value: "buy_request", label: "Buy Request" },
  { value: "sell_offer", label: "Sell Offer" },
  { value: "deal", label: "Deal" },
  { value: "price_quote", label: "Price Quote" },
  { value: "news", label: "News" },
];

const URGENCY_OPTIONS = [
  { value: "", label: "All Urgencies" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

export interface FeedFilterValues {
  period: string;
  kind: string;
  source: string;
  urgency: string;
}

interface FeedFiltersProps {
  /** Extra class names for the container */
  className?: string;
  /** Compact mode for embedding in panels */
  compact?: boolean;
}

export function FeedFilters({ className = "", compact = false }: FeedFiltersProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const period = searchParams.get("period") ?? "30d";
  const kind = searchParams.get("kind") ?? "";
  const source = searchParams.get("source") ?? "";
  const urgency = searchParams.get("urgency") ?? "";

  const updateParam = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  const selectClass =
    "rounded-md border border-border bg-background-tertiary px-3 py-1.5 text-sm text-foreground " +
    "focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background " +
    "hover:bg-background-tertiary transition-colors";

  if (compact) {
    return (
      <div className={`flex flex-wrap items-center gap-2 ${className}`}>
        <select
          value={period}
          onChange={(e) => updateParam("period", e.target.value)}
          className={selectClass}
          aria-label="Filter by period"
        >
          {PERIOD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={kind}
          onChange={(e) => updateParam("kind", e.target.value)}
          className={selectClass}
          aria-label="Filter by kind"
        >
          {KIND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={urgency}
          onChange={(e) => updateParam("urgency", e.target.value)}
          className={selectClass}
          aria-label="Filter by urgency"
        >
          {URGENCY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className={`flex flex-wrap items-center gap-3 ${className}`}>
      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          Period
        </label>
        <select
          value={period}
          onChange={(e) => updateParam("period", e.target.value)}
          className={selectClass}
          aria-label="Filter by period"
        >
          {PERIOD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          Kind
        </label>
        <select
          value={kind}
          onChange={(e) => updateParam("kind", e.target.value)}
          className={selectClass}
          aria-label="Filter by kind"
        >
          {KIND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          Source
        </label>
        <input
          type="text"
          value={source}
          onChange={(e) => updateParam("source", e.target.value)}
          placeholder="All sources"
          className={`${selectClass} min-w-[120px]`}
          aria-label="Filter by source"
        />
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          Urgency
        </label>
        <select
          value={urgency}
          onChange={(e) => updateParam("urgency", e.target.value)}
          className={selectClass}
          aria-label="Filter by urgency"
        >
          {URGENCY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
