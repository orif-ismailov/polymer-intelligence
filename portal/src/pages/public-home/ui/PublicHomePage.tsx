import { usePublicOffers } from "@/entities/public";
import { Seo, useCanonical } from "@/shared/seo";
import { publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { Skeleton } from "@/shared/ui";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { CatalogSidebar } from "./CatalogSidebar";
import { DirectoryStrip } from "./DirectoryStrip";
import { HeroBanner } from "./HeroBanner";
import { HomeOfferCard } from "./HomeOfferCard";
import { MarketRail } from "./MarketRail";
import { ProofBand } from "./ProofBand";
import { VerifiedManufacturers } from "./VerifiedManufacturers";

/**
 * Public storefront home — layout locked to `docs/new-design/marketplace.jpeg`.
 */
export function PublicHomePage() {
  const { t, i18n } = useTranslation();
  const origin = publicSiteOrigin();
  const { canonical, alternates } = useCanonical(origin, "/", SUPPORTED_LANGS, i18n.language);
  const featured = usePublicOffers({}, 0, 4);

  const jsonLd: Array<Record<string, unknown>> = [
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "IMEX AI",
      url: origin || undefined,
      description: t("public.home.metaDescription"),
    },
    {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: "IMEX AI",
      url: origin || undefined,
      potentialAction: {
        "@type": "SearchAction",
        target: `${origin}/market?q={search_term_string}`,
        "query-input": "required name=search_term_string",
      },
    },
  ];

  return (
    <>
      <Seo
        title={t("public.home.metaTitle")}
        description={t("public.home.metaDescription")}
        canonical={canonical}
        alternates={alternates}
        jsonLd={jsonLd}
      />

      {/* 1. Hero — full-bleed band, dissolving into the page at both ends. */}
      <HeroBanner />

      {/* 2. Six directory / surface cards */}
      <DirectoryStrip />

      {/* 3. Marketplace body: categories+filters | products+manufacturers | rail */}
      <section aria-labelledby="catalog-heading" className="bg-bg">
        <div className="mx-auto max-w-[1440px] px-4 py-4 lg:px-6">
          {/* 229 / 1fr / 330 with a 14px gutter — measured off the mockup's
              sidebar 24→253, main 267→1075 and rail 1086→1416. */}
          <div className="grid gap-3.5 lg:grid-cols-[14.3125rem_minmax(0,1fr)] xl:grid-cols-[14.3125rem_minmax(0,1fr)_20.625rem]">
            <CatalogSidebar />

            {/* Products and manufacturers are two panels stacked in the middle
                column, each on the same `surface` tone as the cards inside it —
                sampled off the mockup, where only the hairlines separate them. */}
            <div className="min-w-0 space-y-3.5">
              <section className="rounded-md border border-border bg-surface p-3.5">
                <div className="flex items-baseline justify-between gap-4">
                  <h2
                    id="catalog-heading"
                    className="text-[15px] font-semibold tracking-tight text-text"
                  >
                    {t("public.home.recommendedProducts")}
                  </h2>
                  <Link
                    to="/market"
                    className="shrink-0 text-[12px] font-medium text-brand hover:underline"
                  >
                    {t("public.home.seeAll")}
                    <span aria-hidden> →</span>
                  </Link>
                </div>

                {featured.isLoading ? (
                  <div className="mt-3.5 grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
                    <Skeleton className="h-[21rem] w-full" />
                    <Skeleton className="h-[21rem] w-full" />
                    <Skeleton className="h-[21rem] w-full" />
                    <Skeleton className="h-[21rem] w-full" />
                  </div>
                ) : featured.data && featured.data.items.length > 0 ? (
                  <div className="mt-3.5 grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
                    {featured.data.items.slice(0, 4).map((offer) => (
                      <HomeOfferCard key={offer.id} offer={offer} />
                    ))}
                  </div>
                ) : (
                  <p className="mt-3.5 rounded-md border border-border bg-surface-inset px-4 py-10 text-center text-sm text-text-muted">
                    {t("public.home.noOffers")}
                  </p>
                )}
              </section>

              <VerifiedManufacturers />
            </div>

            <aside className="min-w-0">
              <MarketRail />
            </aside>
          </div>
        </div>
      </section>

      {/* 4. Closing band — why IMEX, the figures that back it, and the join CTA.
             Full-bleed, mirroring the hero, so the page bookends its two
             persuasive moments around the dense marketplace body. */}
      <ProofBand />
    </>
  );
}
