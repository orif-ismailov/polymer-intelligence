import { ArrowDownRight, ArrowUpRight, FlaskConical, FileCheck2, Truck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { usePublicNews, usePublicPrices } from "@/entities/public";
import { cn, formatDateShort } from "@/shared/lib";
import { Skeleton } from "@/shared/ui";

/**
 * Right rail from `marketplace.jpeg` §4: market prices, industry news, popular
 * services — 330px wide, and much denser than the cabinet default. The mockup
 * runs price rows at ~23px and 12px type; an earlier pass at `text-sm py-2.5`
 * made this column nearly twice as tall as the products beside it.
 */
export function MarketRail() {
  const { t, i18n } = useTranslation();
  const prices = usePublicPrices(6);
  const news = usePublicNews(3);
  // Freshest observation across the rail — the quotes are ordered by product,
  // not by date, so the newest row is not necessarily the first one.
  const observedOn = prices.data?.reduce<string | null>(
    (latest, row) => (latest == null || row.observed_on > latest ? row.observed_on : latest),
    null,
  );

  const services = [
    {
      key: "logistics",
      to: "/logistics",
      icon: <Truck size={20} strokeWidth={1.5} aria-hidden />,
      title: t("public.home.service.logistics.title"),
      body: t("public.home.service.logistics.body"),
    },
    {
      key: "customs",
      to: "/logistics",
      icon: <FileCheck2 size={20} strokeWidth={1.5} aria-hidden />,
      title: t("public.home.service.customs.title"),
      body: t("public.home.service.customs.body"),
    },
    {
      key: "lab",
      to: "/laboratories",
      icon: <FlaskConical size={20} strokeWidth={1.5} aria-hidden />,
      title: t("public.home.service.lab.title"),
      body: t("public.home.service.lab.body"),
    },
  ];

  return (
    /*
     * Vertical rail at `xl`, three-up strip at `lg`. Between 1024 and 1279 the
     * page grid has no third column for this to live in, so the cards run
     * side by side across the full width instead of stacking into a sliver —
     * see the `lg:col-span-2` note in `PublicHomePage`. `items-start` so the
     * three cards keep their own heights rather than stretching to the tallest.
     */
    <div className="space-y-3 lg:grid lg:grid-cols-3 lg:items-start lg:gap-3.5 lg:space-y-0 xl:block xl:space-y-2">
      <section
        aria-labelledby="rail-prices"
        className="rounded-md border border-border bg-surface"
      >
        <div className="flex items-baseline justify-between gap-2 border-b border-border px-3.5 py-2.5">
          <h2 id="rail-prices" className="text-[15px] font-semibold text-text">
            {t("public.home.marketPrices")}
          </h2>
          <Link to="/prices" className="text-[12px] font-medium text-brand hover:underline">
            {t("public.home.seeAll")}
            <span aria-hidden> →</span>
          </Link>
        </div>

        {prices.isLoading ? (
          <div className="space-y-3 p-4">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-full" />
          </div>
        ) : prices.data && prices.data.length > 0 ? (
          <>
            <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-x-3 px-3.5 pb-1.5 pt-2.5 text-[11px] text-text-subtle">
              <span>{t("public.home.priceProduct")}</span>
              <span className="text-end">{t("public.home.priceValueUsd")}</span>
              <span className="text-end">{t("public.home.priceChange24h")}</span>
            </div>
            <ul className="pb-1">
              {prices.data.map((row) => {
                const change = row.change_pct == null ? null : Number(row.change_pct);
                return (
                  <li key={row.product_id}>
                    <Link
                      to={`/market?product_id=${row.product_id}`}
                      /* 3px of padding is a 22px row — right for the 330px rail
                         at `xl`, where the mockup runs these dense and a mouse
                         is doing the pointing, and unusable on a phone. Below
                         `xl` the rail is full width, so the rows take the
                         height they need to be tappable. */
                      className="grid min-h-11 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 px-3.5 transition-colors hover:bg-surface-2 xl:min-h-0 xl:py-[0.1875rem]"
                    >
                      <span className="num truncate text-[12px] text-text">
                        {row.code}
                      </span>
                      {/* Thousands-grouped and rounded, as in the mockup — the
                          wire value is a Decimal string like "1087.34", and two
                          decimals of a market quote is precision it doesn't have. */}
                      <span className="num text-[12px] font-medium text-text">
                        {Number(row.price).toLocaleString(i18n.language, {
                          maximumFractionDigits: 0,
                        })}
                      </span>
                      <span
                        className={cn(
                          "num inline-flex min-w-[3.25rem] items-center justify-end gap-0.5 text-[11px] font-medium",
                          change == null
                            ? "text-text-subtle"
                            : change > 0
                              ? "text-success"
                              : change < 0
                                ? "text-danger"
                                : "text-text-muted",
                        )}
                      >
                        {change == null ? (
                          t("public.home.noHistory")
                        ) : (
                          <>
                            {change > 0 ? (
                              <ArrowUpRight size={12} strokeWidth={2} aria-hidden />
                            ) : change < 0 ? (
                              <ArrowDownRight size={12} strokeWidth={2} aria-hidden />
                            ) : null}
                            {`${change > 0 ? "+" : ""}${change}%`}
                          </>
                        )}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
            {/* Two-up footer, as in the mockup. The right side is the real
                `observed_on` of the freshest quote — the mockup's "Обновлено:
                10:30" against a daily observation would be a fake precision. */}
            {/* Stacked until `xl`. Side by side, the source line had to
                `truncate` to «Источник: рыночные наблюдения пла…» — a
                provenance note that stops mid-word tells the reader less than
                nothing. It only truly fits in the 330px rail at `xl`, which is
                the one width that keeps the mockup's two-up footer. */}
            <div className="flex flex-col gap-0.5 border-t border-border px-3.5 py-2 text-[10px] text-text-subtle xl:flex-row xl:items-baseline xl:justify-between xl:gap-2">
              <span className="xl:truncate">{t("public.home.priceSource")}</span>
              {observedOn ? (
                <span className="num shrink-0">
                  {t("public.home.priceUpdated", { date: formatDateShort(observedOn) })}
                </span>
              ) : null}
            </div>
          </>
        ) : (
          <p className="px-3.5 py-8 text-[12px] text-text-muted">{t("public.home.noPrices")}</p>
        )}
      </section>

      <section
        aria-labelledby="rail-news"
        className="rounded-md border border-border bg-surface"
      >
        <div className="flex items-baseline justify-between gap-2 border-b border-border px-3.5 py-2.5">
          <h2 id="rail-news" className="text-[15px] font-semibold text-text">
            {t("public.home.industryNews")}
          </h2>
          <Link to="/news" className="text-[12px] font-medium text-brand hover:underline">
            {t("public.home.seeAll")}
            <span aria-hidden> →</span>
          </Link>
        </div>

        {news.isLoading ? (
          <div className="space-y-3 p-4">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : news.data && news.data.length > 0 ? (
          <ul className="divide-y divide-border">
            {news.data.map((article) => (
              <li key={article.id}>
                <Link
                  to={`/news/${article.id}`}
                  className="flex gap-2.5 px-3.5 py-2.5 transition-colors hover:bg-surface-2"
                >
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border border-gold-line bg-gold-soft text-gold">
                    <FileCheck2 size={15} strokeWidth={1.75} aria-hidden />
                  </span>
                  <span className="min-w-0">
                    {article.published_at ? (
                      <time
                        dateTime={article.published_at}
                        className="num block text-[11px] text-text-subtle"
                      >
                        {new Date(article.published_at).toLocaleDateString()}
                      </time>
                    ) : null}
                    <span className="mt-0.5 line-clamp-2 text-[12px] leading-[1.4] text-text">
                      {article.headline}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-3.5 py-6 text-[12px] text-text-muted">{t("public.home.noNews")}</p>
        )}
      </section>

      <section
        aria-labelledby="rail-services"
        className="rounded-md border border-border bg-surface p-3.5"
      >
        <h2 id="rail-services" className="text-[15px] font-semibold text-text">
          {t("public.home.popularServices")}
        </h2>
        <ul className="mt-2.5 space-y-2">
          {services.map((service) => (
            <li key={service.key}>
              <Link
                to={service.to}
                className="flex min-h-11 items-center gap-2.5 rounded-sm py-1 transition-colors hover:bg-surface-2 xl:min-h-0 xl:items-start xl:py-0"
              >
                <span className="shrink-0 text-gold xl:mt-0.5">{service.icon}</span>
                <span className="min-w-0">
                  <span className="block text-[12px] font-medium leading-[1.35] text-text">
                    {service.title}
                  </span>
                  <span className="block text-[11px] leading-[1.35] text-text-muted">
                    {service.body}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {/* The mockup moves "Все услуги" out of the header and onto a
            full-width outline button at the card's foot. */}
        <Link
          to="/logistics"
          className="mt-3 flex h-11 items-center justify-center rounded-sm border border-border-strong text-[12px] font-medium text-text transition-colors hover:border-brand-line hover:bg-brand-soft hover:text-brand xl:h-8"
        >
          {t("public.home.allServices")}
        </Link>
      </section>
    </div>
  );
}
