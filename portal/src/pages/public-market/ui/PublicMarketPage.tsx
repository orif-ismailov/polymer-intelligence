import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import {
  PublicOfferTile,
  usePublicCategories,
  usePublicOffers,
  type PublicOfferFilters,
} from "@/entities/public";
import { publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { cn } from "@/shared/lib";
import { Seo, useCanonical } from "@/shared/seo";
import { Skeleton } from "@/shared/ui";

const PAGE_SIZE = 24;

/**
 * `/market` — the public catalog.
 *
 * Every filter lives in the query string rather than component state. That is
 * what makes a filtered view linkable ("here is the PP in stock in Uzbekistan"),
 * what lets the server render the same page the browser would, and what lets the
 * back button work. The cabinet's market screen keeps its filters in `useState`,
 * which is fine behind a login and wrong in front of one.
 *
 * Filtered views are `noindex`: a crawler that follows every filter combination
 * finds thousands of near-duplicate pages, all of which dilute the one that
 * should rank. The unfiltered catalog indexes normally.
 */
export function PublicMarketPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const origin = publicSiteOrigin();
  const { canonical, alternates } = useCanonical(
    origin,
    "/market",
    SUPPORTED_LANGS,
    i18n.language,
  );

  const q = params.get("q") ?? "";
  const productId = params.get("product_id");
  // Set by «Смотреть все» on a company profile. It has no control in the rail —
  // it is a scope the visitor arrived with, cleared by «Сбросить» like any other.
  const sellerCompanyId = params.get("seller_company_id");
  const availability = params.get("availability") ?? "";
  const country = (params.get("country") ?? "").toUpperCase();
  const labVerified = params.get("lab_verified") === "1";
  const hasPassport = params.get("has_lab_passport") === "1";
  const offset = Math.max(0, Number(params.get("offset") ?? 0) || 0);

  const isFiltered =
    Boolean(q || productId || sellerCompanyId || availability || country) ||
    labVerified ||
    hasPassport;

  const filters: PublicOfferFilters = {
    q: q || undefined,
    product_id: productId ? Number(productId) : undefined,
    seller_company_id:
      sellerCompanyId && /^\d+$/.test(sellerCompanyId) ? Number(sellerCompanyId) : undefined,
    availability: availability === "in_stock" || availability === "on_order" ? availability : undefined,
    country: country || undefined,
    lab_verified: labVerified || undefined,
    has_lab_passport: hasPassport || undefined,
  };

  const categories = usePublicCategories();
  const offers = usePublicOffers(filters, offset, PAGE_SIZE);
  const total = offers.data?.total ?? 0;

  /** Write one filter into the URL, always resetting to the first page. */
  function setFilter(key: string, value: string | null): void {
    const next = new URLSearchParams(params);
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
    next.delete("offset");
    setParams(next, { replace: false });
  }

  function goToOffset(nextOffset: number): void {
    const next = new URLSearchParams(params);
    if (nextOffset <= 0) next.delete("offset");
    else next.set("offset", String(nextOffset));
    setParams(next);
  }

  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        {
          "@type": "ListItem",
          position: 1,
          name: t("public.nav.home"),
          item: `${origin}/`,
        },
        {
          "@type": "ListItem",
          position: 2,
          name: t("public.market.title"),
          item: `${origin}/market`,
        },
      ],
    },
  ];

  return (
    <>
      <Seo
        title={t("public.market.metaTitle")}
        description={t("public.market.metaDescription")}
        canonical={canonical}
        alternates={isFiltered ? undefined : alternates}
        noindex={isFiltered}
        jsonLd={jsonLd}
      />

      <div className="mx-auto max-w-[1440px] px-4 py-10 lg:px-6">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight text-text">
            {t("public.market.title")}
          </h1>
          <p className="mt-1 text-sm text-text-muted">{t("public.market.subtitle")}</p>
        </header>

        <div className="mt-8 grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
          {/* Filter rail. A real form region, labelled, keyboard-reachable. */}
          <aside aria-label={t("public.market.filters")} className="min-w-0 space-y-6">
            <div>
              <label
                htmlFor="market-q"
                className="block text-xs font-medium text-text-muted"
              >
                {t("public.market.search")}
              </label>
              <input
                id="market-q"
                type="search"
                defaultValue={q}
                onBlur={(e) => setFilter("q", e.target.value.trim() || null)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setFilter("q", (e.target as HTMLInputElement).value.trim() || null);
                  }
                }}
                placeholder={t("public.market.searchPlaceholder")}
                className="mt-1.5 h-10 w-full rounded-md border border-border bg-surface-inset px-3 text-sm text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              />
            </div>

            <div>
              <span className="block text-xs font-medium text-text-muted">
                {t("public.market.category")}
              </span>
              {categories.isLoading ? (
                <div className="mt-2 space-y-1.5">
                  <Skeleton className="h-5 w-full" />
                  <Skeleton className="h-5 w-full" />
                </div>
              ) : (
                <ul className="mt-2 space-y-0.5">
                  <li>
                    <button
                      type="button"
                      onClick={() => setFilter("product_id", null)}
                      className={cn(
                        "flex w-full items-baseline justify-between gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                        !productId
                          ? "bg-brand-soft text-brand"
                          : "text-text-muted hover:bg-surface-2 hover:text-text",
                      )}
                    >
                      {t("public.market.allCategories")}
                    </button>
                  </li>
                  {(categories.data ?? []).map((cat) => (
                    <li key={cat.product_id}>
                      <button
                        type="button"
                        onClick={() => setFilter("product_id", String(cat.product_id))}
                        className={cn(
                          "flex w-full items-baseline justify-between gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                          productId === String(cat.product_id)
                            ? "bg-brand-soft text-brand"
                            : "text-text-muted hover:bg-surface-2 hover:text-text",
                        )}
                      >
                        <span className="truncate">{cat.label}</span>
                        <span className="num shrink-0 text-xs text-text-subtle">
                          {cat.offer_count}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <label
                htmlFor="market-availability"
                className="block text-xs font-medium text-text-muted"
              >
                {t("public.market.availability")}
              </label>
              <select
                id="market-availability"
                value={availability}
                onChange={(e) => setFilter("availability", e.target.value || null)}
                className="mt-1.5 h-10 w-full rounded-md border border-border bg-surface-inset px-3 text-sm text-text focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <option value="">{t("public.market.any")}</option>
                <option value="in_stock">{t("availability.in_stock")}</option>
                <option value="on_order">{t("availability.on_order")}</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="market-country"
                className="block text-xs font-medium text-text-muted"
              >
                {t("public.market.country")}
              </label>
              <input
                id="market-country"
                type="text"
                maxLength={2}
                defaultValue={country}
                onBlur={(e) =>
                  setFilter("country", e.target.value.trim().toUpperCase() || null)
                }
                placeholder="UZ"
                className="num mt-1.5 h-10 w-full rounded-md border border-border bg-surface-inset px-3 text-sm uppercase text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              />
            </div>

            <fieldset>
              <legend className="text-xs font-medium text-text-muted">
                {t("public.market.laboratory")}
              </legend>
              <div className="mt-2 space-y-2">
                <label className="flex items-center gap-2 text-sm text-text-muted">
                  <input
                    type="checkbox"
                    checked={hasPassport}
                    onChange={(e) => setFilter("has_lab_passport", e.target.checked ? "1" : null)}
                    className="h-4 w-4 rounded-sm border-border-strong bg-surface-inset accent-brand"
                  />
                  {t("public.market.hasPassport")}
                </label>
                <label className="flex items-center gap-2 text-sm text-text-muted">
                  <input
                    type="checkbox"
                    checked={labVerified}
                    onChange={(e) => setFilter("lab_verified", e.target.checked ? "1" : null)}
                    className="h-4 w-4 rounded-sm border-border-strong bg-surface-inset accent-brand"
                  />
                  {t("public.market.labVerified")}
                </label>
              </div>
            </fieldset>

            {isFiltered ? (
              <Link
                to="/market"
                className="inline-block text-sm text-brand hover:underline"
              >
                {t("public.market.reset")}
              </Link>
            ) : null}
          </aside>

          <div className="min-w-0">
            <p className="text-sm text-text-muted" aria-live="polite">
              {offers.isLoading ? (
                <Skeleton className="h-5 w-40" />
              ) : (
                t("public.market.resultCount", { count: total })
              )}
            </p>

            {offers.isLoading ? (
              <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                <Skeleton className="h-72 w-full" />
                <Skeleton className="h-72 w-full" />
                <Skeleton className="h-72 w-full" />
              </div>
            ) : offers.isError ? (
              <p className="mt-4 rounded-lg border border-border bg-surface px-4 py-10 text-center text-sm text-text-muted">
                {t("errors.loadFailed")}
              </p>
            ) : offers.data && offers.data.items.length > 0 ? (
              <>
                <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {offers.data.items.map((offer) => (
                    <PublicOfferTile key={offer.id} offer={offer} />
                  ))}
                </div>

                {total > PAGE_SIZE ? (
                  <nav
                    aria-label={t("public.market.pagination")}
                    className="mt-8 flex items-center justify-between gap-4"
                  >
                    <button
                      type="button"
                      disabled={offset === 0}
                      onClick={() => goToOffset(offset - PAGE_SIZE)}
                      className="rounded-md border border-border-strong px-4 py-2 text-sm font-medium text-text transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-text-subtle disabled:hover:bg-transparent"
                    >
                      {t("common.prev")}
                    </button>
                    <span className="num text-sm text-text-muted">
                      {t("public.market.pageOf", {
                        page: Math.floor(offset / PAGE_SIZE) + 1,
                        pages: Math.max(1, Math.ceil(total / PAGE_SIZE)),
                      })}
                    </span>
                    <button
                      type="button"
                      // A real end, from the real total. No guessing from a short page.
                      disabled={offset + PAGE_SIZE >= total}
                      onClick={() => goToOffset(offset + PAGE_SIZE)}
                      className="rounded-md border border-border-strong px-4 py-2 text-sm font-medium text-text transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-text-subtle disabled:hover:bg-transparent"
                    >
                      {t("common.next")}
                    </button>
                  </nav>
                ) : null}
              </>
            ) : (
              <p className="mt-4 rounded-lg border border-border bg-surface px-4 py-10 text-center text-sm text-text-muted">
                {t("public.market.empty")}
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
