import { useState } from "react";

import { SlidersHorizontal } from "lucide-react";
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
import { useSyncedDraft } from "@/shared/lib";
import { Seo, useCanonical } from "@/shared/seo";
import { Dialog, SearchIcon, Skeleton, buttonClasses } from "@/shared/ui";

import { MarketFilters, type MarketFilterState } from "./MarketFilters";

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

  const [filtersOpen, setFiltersOpen] = useState(false);
  // Re-syncs when «Сбросить» or back/forward changes `q` under the sticky bar.
  const [qDraft, setQDraft] = useSyncedDraft(q);

  const filterState: MarketFilterState = {
    q,
    productId,
    availability,
    country,
    labVerified,
    hasPassport,
  };

  /*
   * What the phone's filter button has to say for itself. With the rail behind a
   * tap, a filter the visitor set is otherwise invisible — the results just look
   * short. `q` is excluded on purpose: it has its own field in the bar, sitting
   * right next to this badge with the term still in it.
   */
  const activeFilterCount =
    (productId ? 1 : 0) +
    (availability ? 1 : 0) +
    (country ? 1 : 0) +
    (sellerCompanyId ? 1 : 0) +
    (labVerified ? 1 : 0) +
    (hasPassport ? 1 : 0);

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

      {/*
        Phone toolbar. `PublicTopNav` is `sticky top-0 z-30` and 64px tall below
        `xl`, so `top-16` parks this immediately under it and the lower z-index
        keeps the header on top when they meet. `PublicShell` puts no `overflow`
        on `<main>`, so sticky needs nothing from the shell.

        It carries the two controls a catalog is useless without — the query and
        the way back to the filters — and it carries them at every scroll
        position, which is the point: the rail it replaces was 682px of form
        that a visitor had to scroll back up through to change one thing.
      */}
      <div className="sticky top-16 z-20 border-b border-border bg-bg/95 lg:hidden">
        <div className="mx-auto flex max-w-[1440px] items-center gap-2 px-4 py-2.5">
          <div className="relative min-w-0 flex-1">
            <label htmlFor="market-q-bar" className="sr-only">
              {t("public.market.search")}
            </label>
            <span
              aria-hidden
              className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-text-subtle"
            >
              <SearchIcon size={16} />
            </span>
            <input
              id="market-q-bar"
              type="search"
              value={qDraft}
              onChange={(e) => setQDraft(e.target.value)}
              onBlur={(e) => setFilter("q", e.target.value.trim() || null)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setFilter("q", (e.target as HTMLInputElement).value.trim() || null);
                  (e.target as HTMLInputElement).blur();
                }
              }}
              placeholder={t("public.market.searchPlaceholder")}
              className="h-11 w-full rounded-md border border-border bg-surface-inset ps-9 pe-3 text-sm text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            />
          </div>

          <button
            type="button"
            onClick={() => setFiltersOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={filtersOpen}
            className="inline-flex h-11 shrink-0 items-center gap-2 rounded-md border border-border-strong px-3.5 text-sm font-medium text-text transition-colors hover:border-brand-line hover:bg-brand-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
          >
            <SlidersHorizontal size={16} strokeWidth={1.75} aria-hidden />
            {t("public.market.filters")}
            {activeFilterCount > 0 ? (
              <span className="num inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-brand px-1 text-[11px] font-semibold text-brand-fg">
                {activeFilterCount}
              </span>
            ) : null}
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-[1440px] px-4 py-6 lg:px-6 lg:py-10">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight text-text">
            {t("public.market.title")}
          </h1>
          <p className="mt-1 text-sm text-text-muted">{t("public.market.subtitle")}</p>
        </header>

        <div className="mt-6 grid gap-8 lg:mt-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
          {/*
            Desktop rail. `lg:sticky`, not `sticky`: a grid item's sticky
            containing block is its grid AREA, and below `lg` this grid is ONE
            column, so the rail's area is the full page height and the pin
            followed the scroll straight down over the results. Measured at
            scrollY 900 on a 390px viewport, the rail held viewport 0-682 while
            the first tile held 62-522 — the two overlapped and the rail's
            labels and selects painted through the product grid. It was broken
            on every phone and every portrait tablet, since the two-column rule
            only starts at 1024.

            `hidden` below `lg` for the same reason it is now redundant there:
            those widths get the sheet.
          */}
          <aside
            aria-label={t("public.market.filters")}
            className="hidden min-w-0 lg:sticky lg:top-6 lg:block lg:self-start"
          >
            <MarketFilters
              idPrefix="market"
              state={filterState}
              categories={categories.data ?? []}
              categoriesLoading={categories.isLoading}
              onChange={setFilter}
            />
            {isFiltered ? (
              <Link
                to="/market"
                className="mt-6 inline-block text-sm text-brand hover:underline"
              >
                {t("public.market.reset")}
              </Link>
            ) : null}
          </aside>

          <div className="min-w-0">
            {/* A `<div>`, not a `<p>`: `Skeleton` renders a `<div>`, and a
                block inside a paragraph is invalid nesting — React warned about
                it on every load of this page. The live region is unaffected. */}
            <div className="text-sm text-text-muted" aria-live="polite">
              {offers.isLoading ? (
                <Skeleton className="h-5 w-40" />
              ) : (
                t("public.market.resultCount", { count: total })
              )}
            </div>

            {offers.isLoading ? (
              <div className="mt-4 grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
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
                <div className="mt-4 grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
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
                      className="inline-flex h-11 items-center rounded-md border border-border-strong px-4 text-sm font-medium text-text transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-text-subtle disabled:hover:bg-transparent"
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
                      className="inline-flex h-11 items-center rounded-md border border-border-strong px-4 text-sm font-medium text-text transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-text-subtle disabled:hover:bg-transparent"
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

      {/*
        The rail, on demand. `placement="sheet"` is a `Dialog` variant rather
        than a new component precisely so this inherits the focus trap, Escape,
        body scroll lock, backdrop and focus restoration that a hand-rolled
        drawer would have to re-earn.

        No «Применить» that applies anything: every control writes straight to
        the query string, so the results behind the sheet are already filtered
        and the primary button only has to dismiss. It states the count instead,
        which is the honest label for what closing reveals — and it doubles as
        live feedback while the visitor is still choosing.

        `hideSearch` because the query lives in the sticky bar this button sits
        in; repeating it here would be two fields for one parameter.
      */}
      <Dialog
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        placement="sheet"
        title={t("public.market.filters")}
        className="lg:hidden"
        footer={
          <>
            <Link
              to="/market"
              onClick={() => setFiltersOpen(false)}
              className={buttonClasses({
                variant: "outline",
                className: "!h-11 shrink-0 px-4",
              })}
            >
              {t("common.clear")}
            </Link>
            <button
              type="button"
              onClick={() => setFiltersOpen(false)}
              className={buttonClasses({ fullWidth: true, className: "!h-11" })}
            >
              {offers.isLoading
                ? t("public.market.showResults")
                : t("public.market.showResultsCount", { count: total })}
            </button>
          </>
        }
      >
        <MarketFilters
          idPrefix="market-sheet"
          state={filterState}
          categories={categories.data ?? []}
          categoriesLoading={categories.isLoading}
          onChange={setFilter}
          hideSearch
        />
      </Dialog>
    </>
  );
}
