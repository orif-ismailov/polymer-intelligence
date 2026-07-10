"use client";

/**
 * RequestsFilterBar — Period / Product / Region / Source selects + "More Filters"
 * + removable active-filter chips + "Clear filters" reset.
 *
 * All filter state is persisted in URL search params via useSearchParams +
 * router.replace (same pattern as FeedFilters from 04-03).
 * No hardcoded hex — token classes only (UI-SPEC §Color).
 */

import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useRouter } from "@/i18n/navigation";
import { X, ChevronDown } from "lucide-react";

// Option VALUES are stable identifiers; displayed labels are translated via t().
const PERIOD_OPTIONS = [
  { value: "7d", labelKey: "periodOpt7d" },
  { value: "30d", labelKey: "periodOpt30d" },
  { value: "90d", labelKey: "periodOpt90d" },
  { value: "all", labelKey: "periodOptAll" },
];

const URGENCY_OPTIONS = [
  { value: "", labelKey: "urgencyOptAll" },
  { value: "high", labelKey: "urgencyOptHigh" },
  { value: "medium", labelKey: "urgencyOptMedium" },
  { value: "low", labelKey: "urgencyOptLow" },
];

const STATUS_OPTIONS = [
  { value: "", labelKey: "statusOptAll" },
  { value: "new", labelKey: "statusOptNew" },
  { value: "viewed", labelKey: "statusOptViewed" },
  { value: "in_progress", labelKey: "statusOptInProgress" },
  { value: "offer_sent", labelKey: "statusOptOfferSent" },
  { value: "matched", labelKey: "statusOptMatched" },
  { value: "closed", labelKey: "statusOptClosed" },
  { value: "cancelled", labelKey: "statusOptCancelled" },
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
  t: (key: string) => string,
): ActiveFilter[] {
  const filters: ActiveFilter[] = [];
  if (period && period !== "all")
    filters.push({
      key: "period",
      label: t("filterPeriod"),
      value: PERIOD_OPTIONS.find((o) => o.value === period)
        ? t(PERIOD_OPTIONS.find((o) => o.value === period)!.labelKey)
        : period,
    });
  if (urgency)
    filters.push({
      key: "urgency",
      label: t("filterUrgency"),
      value: URGENCY_OPTIONS.find((o) => o.value === urgency)
        ? t(URGENCY_OPTIONS.find((o) => o.value === urgency)!.labelKey)
        : urgency,
    });
  if (status)
    filters.push({
      key: "status",
      label: t("filterStatus"),
      value: STATUS_OPTIONS.find((o) => o.value === status)
        ? t(STATUS_OPTIONS.find((o) => o.value === status)!.labelKey)
        : status,
    });
  if (product)
    filters.push({ key: "product", label: t("filterProduct"), value: product });
  return filters;
}

export function RequestsFilterBar() {
  const t = useTranslations("requests");
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

  const activeFilters = getActiveFilters(period, urgency, status, product, t);

  return (
    <div className="flex flex-col gap-3">
      {/* Filter selects row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Period */}
        <div className="relative">
          <label htmlFor="filter-period" className="sr-only">
            {t("filterPeriod")}
          </label>
          <select
            id="filter-period"
            value={period}
            onChange={(e) => setParam("period", e.target.value)}
            className="h-8 rounded-lg border border-border bg-background-secondary px-2.5 pe-8 text-sm text-foreground appearance-none cursor-pointer hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {PERIOD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey)}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute end-2 top-1/2 -translate-y-1/2 text-foreground-muted"
            aria-hidden="true"
          />
        </div>

        {/* Urgency */}
        <div className="relative">
          <label htmlFor="filter-urgency" className="sr-only">
            {t("filterUrgency")}
          </label>
          <select
            id="filter-urgency"
            value={urgency}
            onChange={(e) => setParam("urgency", e.target.value)}
            className="h-8 rounded-lg border border-border bg-background-secondary px-2.5 pe-8 text-sm text-foreground appearance-none cursor-pointer hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {URGENCY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey)}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute end-2 top-1/2 -translate-y-1/2 text-foreground-muted"
            aria-hidden="true"
          />
        </div>

        {/* Status */}
        <div className="relative">
          <label htmlFor="filter-status" className="sr-only">
            {t("filterStatus")}
          </label>
          <select
            id="filter-status"
            value={status}
            onChange={(e) => setParam("status", e.target.value)}
            className="h-8 rounded-lg border border-border bg-background-secondary px-2.5 pe-8 text-sm text-foreground appearance-none cursor-pointer hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey)}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute end-2 top-1/2 -translate-y-1/2 text-foreground-muted"
            aria-hidden="true"
          />
        </div>

        {/* More Filters placeholder button */}
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background-secondary px-3 text-sm text-foreground-muted hover:bg-background-tertiary hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {t("moreFilters")}
          <ChevronDown size={14} aria-hidden="true" />
        </button>

        {/* Clear filters — only visible when active filters exist */}
        {activeFilters.length > 0 && (
          <button
            type="button"
            onClick={clearFilters}
            className="text-sm text-accent hover:underline transition-colors"
          >
            {t("clearFilters")}
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
                className="ms-0.5 rounded-full text-foreground-muted hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                aria-label={t("removeFilter", { label: f.label })}
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
