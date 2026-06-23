/**
 * Offers page — LiveFeedTable pre-filtered to kind=sell_offer.
 * UI-SPEC §Signals/Offers: "/offers: pre-filtered kind='sell_offer'".
 */

import { Suspense } from "react";

import { LiveFeedTable } from "@/components/feed/LiveFeedTable";
import { FeedFilters } from "@/components/feed/FeedFilters";

function FeedLoadingFallback() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      <span className="ml-3 text-sm text-foreground-muted">Loading…</span>
    </div>
  );
}

export default function OffersPage() {
  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Seller Offers</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Active sell offers from exchanges and monitored sources
        </p>
      </div>

      <Suspense fallback={null}>
        {/* Period/source/urgency filters — kind is pre-set to sell_offer */}
        <FeedFilters />
      </Suspense>

      <Suspense fallback={<FeedLoadingFallback />}>
        {/* kind=sell_offer pre-filtered via defaultKind prop */}
        <LiveFeedTable defaultKind="sell_offer" />
      </Suspense>
    </div>
  );
}
