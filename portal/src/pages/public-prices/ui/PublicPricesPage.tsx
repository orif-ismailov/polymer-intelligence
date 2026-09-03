import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { usePublicPrices } from "@/entities/public";
import { publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { cn, useTierBase } from "@/shared/lib";
import { Seo, useCanonical } from "@/shared/seo";
import { PageShell, Skeleton } from "@/shared/ui";

/**
 * `/prices` — the market quote table.
 *
 * A single dense table rather than a grid of cards: these numbers are read down
 * a column and compared, which is exactly the case where a card per row makes
 * comparison harder. `.num` keeps the digits from jittering between refreshes.
 */
export function PublicPricesPage() {
  const base = useTierBase();
  const { t, i18n } = useTranslation();
  const origin = publicSiteOrigin();
  const { canonical, alternates } = useCanonical(
    origin,
    "/prices",
    SUPPORTED_LANGS,
    i18n.language,
  );
  const prices = usePublicPrices(40);

  return (
    <>
      <Seo
        title={t("public.prices.metaTitle")}
        description={t("public.prices.metaDescription")}
        canonical={canonical}
        alternates={alternates}
      />

      <PageShell width="storefront">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight text-text">
            {t("public.prices.title")}
          </h1>
          <p className="mt-1 max-w-[70ch] text-sm text-text-muted">
            {t("public.prices.subtitle")}
          </p>
        </header>

        {prices.isLoading ? (
          <div className="mt-8 space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : prices.data && prices.data.length > 0 ? (
          <div className="mt-8 overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[36rem] text-sm">
              <caption className="sr-only">{t("public.prices.title")}</caption>
              <thead className="bg-surface">
                <tr className="text-xs text-text-subtle">
                  <th scope="col" className="px-4 py-3 text-start font-medium">
                    {t("public.home.priceProduct")}
                  </th>
                  <th scope="col" className="px-4 py-3 text-end font-medium">
                    {t("public.home.priceValue")}
                  </th>
                  <th scope="col" className="px-4 py-3 text-end font-medium">
                    {t("public.prices.unit")}
                  </th>
                  <th scope="col" className="px-4 py-3 text-end font-medium">
                    {t("public.home.priceChange")}
                  </th>
                  <th scope="col" className="px-4 py-3 text-end font-medium">
                    {t("public.prices.observed")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {prices.data.map((row) => {
                  const change = row.change_pct == null ? null : Number(row.change_pct);
                  return (
                    <tr key={row.product_id} className="border-t border-border bg-surface/50">
                      <th scope="row" className="px-4 py-3 text-start font-normal">
                        <Link
                          to={`${base}/market?product_id=${row.product_id}`}
                          className="text-text hover:text-brand"
                        >
                          <span className="num font-medium">{row.code}</span>
                          <span className="ms-2 text-text-muted">{row.label}</span>
                        </Link>
                      </th>
                      <td className="num whitespace-nowrap px-4 py-3 text-end font-medium text-text">
                        {row.price} {row.currency}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-end text-text-muted">
                        {row.unit}
                      </td>
                      <td
                        className={cn(
                          "num whitespace-nowrap px-4 py-3 text-end font-medium",
                          change == null
                            ? "text-text-subtle"
                            : change > 0
                              ? "text-success"
                              : change < 0
                                ? "text-danger"
                                : "text-text-muted",
                        )}
                      >
                        {change == null
                          ? t("public.home.noHistory")
                          : `${change > 0 ? "+" : ""}${change}%`}
                      </td>
                      <td className="num whitespace-nowrap px-4 py-3 text-end text-text-subtle">
                        <time dateTime={row.observed_on}>{row.observed_on}</time>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-8 rounded-lg border border-border bg-surface px-4 py-12 text-center text-sm text-text-muted">
            {t("public.home.noPrices")}
          </p>
        )}
      </PageShell>
    </>
  );
}
