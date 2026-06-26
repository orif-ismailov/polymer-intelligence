"use client";

/**
 * NeedsReviewChip — "Needs Review" filter chip.
 * Phase 5: Enabled as a real toggle that filters the feed to ai.needs_review=true signals.
 * Previously: disabled stub "Available after Phase 5 AI" (Phase 4 placeholder removed).
 */

import { useTranslations } from "next-intl";

interface NeedsReviewChipProps {
  active: boolean;
  onToggle: () => void;
}

export function NeedsReviewChip({ active, onToggle }: NeedsReviewChipProps) {
  const t = useTranslations("common");
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      className={[
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
        active
          ? "border-accent bg-accent text-foreground-on-accent"
          : "border-border bg-background-secondary text-foreground-subtle hover:border-accent hover:text-foreground",
      ].join(" ")}
    >
      {t("needsReview")}
    </button>
  );
}
