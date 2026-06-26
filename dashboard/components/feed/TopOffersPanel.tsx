"use client";

/**
 * TopOffersPanel — compact "Top Seller Offers" list for the Dashboard home.
 *
 * Data comes from the dashboard summary (fetched ONCE on the page) and is passed
 * in as a prop. Shows product, grade, volume, price + currency, region.
 * "View all" links to /offers.
 *
 * No hardcoded hex — token classes only.
 */

import { Store } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import type { DashboardTopOffer } from "@/hooks/useDashboardSummary";

interface TopOffersPanelProps {
  offers?: DashboardTopOffer[];
  isLoading?: boolean;
}

export function TopOffersPanel({ offers, isLoading = false }: TopOffersPanelProps) {
  const t = useTranslations("home");
  return (
    <div className="rounded-lg bg-background-secondary border border-border">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <h2 className="text-base font-semibold text-foreground">{t("topSellerOffers")}</h2>
        <Link
          href="/offers"
          className="text-sm text-accent hover:text-accent-light transition-colors"
        >
          {t("viewAll")}
        </Link>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          <span className="ml-3 text-sm text-foreground-muted">{t("loading")}</span>
        </div>
      ) : !offers?.length ? (
        <div className="flex flex-col items-center justify-center gap-2 py-10">
          <Store size={28} className="text-foreground-muted" aria-hidden="true" />
          <p className="text-sm text-foreground-muted">{t("noOffers")}</p>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {offers.map((offer) => (
            <li key={offer.id} className="flex items-center gap-4 px-6 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-foreground">
                  {offer.product ?? "—"}
                  {offer.grade_text ? (
                    <span className="font-normal text-foreground-muted">
                      {" · "}
                      {offer.grade_text}
                    </span>
                  ) : null}
                </p>
                {offer.region ? (
                  <p className="text-xs text-foreground-muted">{offer.region}</p>
                ) : null}
              </div>
              <span className="hidden whitespace-nowrap text-sm font-mono text-foreground sm:block">
                {offer.volume != null ? t("volumeMt", { volume: offer.volume }) : "—"}
              </span>
              <span className="whitespace-nowrap text-sm font-mono text-foreground">
                {offer.price != null
                  ? t("pricePerMt", {
                      price: offer.price,
                      currency: offer.currency ?? "USD",
                    })
                  : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
