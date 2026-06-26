"use client";

/**
 * FeedFilters — period/product/kind/source/urgency selects for the Live Market Feed.
 * Filters are persisted in URL search params (useSearchParams).
 * UI-SPEC §Live Market Feed panel filter bar.
 */

import { useCallback } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useRouter, usePathname } from "@/i18n/navigation";

const PERIOD_OPTIONS = [
  { value: "7d", labelKey: "7d" },
  { value: "30d", labelKey: "30d" },
  { value: "90d", labelKey: "90d" },
];

const KIND_OPTIONS = [
  { value: "", labelKey: "all" },
  { value: "buy_request", labelKey: "buy_request" },
  { value: "sell_offer", labelKey: "sell_offer" },
  { value: "deal", labelKey: "deal" },
  { value: "price_quote", labelKey: "price_quote" },
  { value: "news", labelKey: "news" },
];

const URGENCY_OPTIONS = [
  { value: "", labelKey: "all" },
  { value: "high", labelKey: "high" },
  { value: "medium", labelKey: "medium" },
  { value: "low", labelKey: "low" },
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
  const t = useTranslations("feed");
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
          aria-label={t("filters.periodLabel")}
        >
          {PERIOD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {t(`period.${o.labelKey}`)}
            </option>
          ))}
        </select>
        <select
          value={kind}
          onChange={(e) => updateParam("kind", e.target.value)}
          className={selectClass}
          aria-label={t("filters.kindLabel")}
        >
          {KIND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {t(`kind.${o.labelKey}`)}
            </option>
          ))}
        </select>
        <select
          value={urgency}
          onChange={(e) => updateParam("urgency", e.target.value)}
          className={selectClass}
          aria-label={t("filters.urgencyLabel")}
        >
          {URGENCY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {t(`urgency.${o.labelKey}`)}
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
          {t("filters.period")}
        </label>
        <select
          value={period}
          onChange={(e) => updateParam("period", e.target.value)}
          className={selectClass}
          aria-label={t("filters.periodLabel")}
        >
          {PERIOD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {t(`period.${o.labelKey}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          {t("filters.kind")}
        </label>
        <select
          value={kind}
          onChange={(e) => updateParam("kind", e.target.value)}
          className={selectClass}
          aria-label={t("filters.kindLabel")}
        >
          {KIND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {t(`kind.${o.labelKey}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          {t("filters.source")}
        </label>
        <input
          type="text"
          value={source}
          onChange={(e) => updateParam("source", e.target.value)}
          placeholder={t("filters.sourcePlaceholder")}
          className={`${selectClass} min-w-[120px]`}
          aria-label={t("filters.sourceLabel")}
        />
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          {t("filters.urgency")}
        </label>
        <select
          value={urgency}
          onChange={(e) => updateParam("urgency", e.target.value)}
          className={selectClass}
          aria-label={t("filters.urgencyLabel")}
        >
          {URGENCY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {t(`urgency.${o.labelKey}`)}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
