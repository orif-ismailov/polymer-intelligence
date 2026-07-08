/**
 * Signals page — full-page LiveFeedTable for all signal kinds.
 *
 * Phase 5: NeedsReviewChip is now a real toggle that filters the feed
 * to ?needs_review=true (signals where ai->>'needs_review'='true').
 */

"use client";

import { useState, Suspense } from "react";
import { useTranslations } from "next-intl";

import { LiveFeedTable } from "@/components/feed/LiveFeedTable";
import { FeedFilters } from "@/components/feed/FeedFilters";
import { NeedsReviewChip } from "./NeedsReviewChip";

function FeedLoadingFallback() {
  const t = useTranslations("signals");
  return (
    <div className="flex items-center justify-center py-8">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      <span className="ms-3 text-sm text-foreground-muted">{t("loading")}</span>
    </div>
  );
}

export default function SignalsPage() {
  const [needsReview, setNeedsReview] = useState(false);
  const t = useTranslations("signals");

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
        <p className="mt-1 text-sm text-foreground-muted">{t("subtitle")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Suspense fallback={null}>
          <FeedFilters />
        </Suspense>
        {/* Needs Review chip — Phase 5: real filter toggle */}
        <NeedsReviewChip
          active={needsReview}
          onToggle={() => setNeedsReview((v) => !v)}
        />
      </div>

      <Suspense fallback={<FeedLoadingFallback />}>
        <LiveFeedTable needsReview={needsReview || undefined} />
      </Suspense>
    </div>
  );
}
