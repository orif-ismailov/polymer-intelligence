/**
 * Offers page — LiveFeedTable pre-filtered to kind=sell_offer.
 * UI-SPEC §Signals/Offers: "/offers: pre-filtered kind='sell_offer'".
 */

import { Suspense } from "react";
import { useTranslations } from "next-intl";

import { LiveFeedTable } from "@/components/feed/LiveFeedTable";
import { FeedFilters } from "@/components/feed/FeedFilters";

function FeedLoadingFallback() {
  const t = useTranslations("offers");
  return (
    <div className="flex items-center justify-center py-8">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      <span className="ms-3 text-sm text-foreground-muted">{t("loading")}</span>
    </div>
  );
}

export default function OffersPage() {
  const t = useTranslations("offers");
  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          {t("subtitle")}
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
