import { useEffect, useState } from "react";

import { SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import {
  NEWS_SCOPES,
  NEWS_SORTS,
  normalizeMarketImpact,
  useNewsArticles,
  useNewsFilterOptions,
  type NewsArticle,
  type NewsFilters as NewsFilterValues,
  type NewsScope,
  type NewsSort,
} from "@/entities/news";
import { publicSiteOrigin } from "@/shared/config";
import { formatDate } from "@/shared/lib";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { Seo, useCanonical } from "@/shared/seo";
import {
  Badge,
  Card,
  CardBody,
  Dialog,
  EmptyState,
  ErrorView,
  NewspaperIcon,
  SearchIcon,
  Skeleton,
  buttonClasses,
} from "@/shared/ui";

import { NewsFilters, type NewsFilterState } from "./ui/NewsFilters";

/**
 * How long the search box waits before it writes to the URL.
 *
 * It has to be a debounce and not an on-blur commit like the market bar's,
 * because this field filters a list the visitor is reading while they type. It
 * also has to reach the *URL* rather than a local state, so the delay is what
 * keeps one history entry per pause instead of one per keystroke.
 */
const SEARCH_DEBOUNCE_MS = 300;

const IMPORTANCE_TONE = { high: "danger", medium: "warning", low: "neutral" } as const;
const IMPACT_TONE = { positive: "success", negative: "danger", neutral: "neutral" } as const;

function ArticleCard({ article }: { article: NewsArticle }) {
  const { t } = useTranslation();
  const importanceTone = IMPORTANCE_TONE[article.importance as keyof typeof IMPORTANCE_TONE];
  // `neutral` is dropped rather than badged: it is the majority value and a row
  // of grey "Neutral" chips is noise on every card that says nothing.
  const impact = normalizeMarketImpact(article.market_impact);

  // `relative` is what the stretched link below anchors to — `Card` itself is
  // static, so without it `after:inset-0` would escape to the nearest positioned
  // ancestor and cover the page.
  return (
    <Card className="relative transition-colors hover:border-brand">
      <CardBody className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {/*
            The Mini App marks these with 🔴/🟡/⚪ and 📈/📉/➖. Here they are
            `Badge` tones, which say the same thing in the palette the rest of
            the app uses — and, unlike an emoji, say it to a screen reader too.
          */}
          {importanceTone ? (
            <Badge tone={importanceTone}>{t(`news.importance.${article.importance}`)}</Badge>
          ) : null}
          {impact && impact !== "neutral" ? (
            <Badge tone={IMPACT_TONE[impact]}>{t(`news.impact.${impact}`)}</Badge>
          ) : null}
          {article.category ? <Badge tone="info">{article.category}</Badge> : null}
        </div>

        {/*
          The whole card is the link, but only the headline is the accessible
          name — a `<Link>` wrapping the summary, the source and four chips reads
          as one enormous label in a rope list. `after:absolute` stretches the
          hit area back over the card without putting any of that in the name.
        */}
        <h2 className="font-semibold text-text">
          <Link
            to={`/news/${article.id}`}
            className="after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {article.headline}
          </Link>
        </h2>

        {article.summary ? (
          <p className="line-clamp-2 text-sm text-text-muted">{article.summary}</p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-text-muted">
          {article.source_name ? <span>{article.source_name}</span> : null}
          {article.merged_count > 1 ? (
            <span className="font-medium text-brand">
              {t("news.moreSources", { count: article.merged_count - 1 })}
            </span>
          ) : null}
          {article.published_at ? (
            <span className="num">· {formatDate(article.published_at)}</span>
          ) : null}
          {article.related_products.slice(0, 3).map((p) => (
            <span key={p} className="rounded-full bg-brand-soft px-2 py-0.5 font-medium text-brand">
              {p}
            </span>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}

/**
 * `/news` — the public news reader.
 *
 * Structure ported from the Mini App's News tab (`webapp/src/pages/News.tsx`):
 * a search box, the four scope tabs, a six-way sort, and live category /
 * country / product facets. What it does NOT port is that page's state model.
 *
 * Every control writes to the query string, because this page is public and
 * server-rendered: the Mini App keeps its filters in `useState`, which is fine
 * inside Telegram and wrong here, where a filtered view has to be linkable, has
 * to render the same on the server as in the browser, and has to answer the back
 * button. Same reasoning as `PublicMarketPage`, and the same `setFilter` shape.
 *
 * Filtered views are `noindex`: a crawler following every facet combination
 * finds thousands of near-duplicate pages that dilute the one that should rank.
 */
export function NewsPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const origin = publicSiteOrigin();
  const { canonical, alternates } = useCanonical(origin, "/news", SUPPORTED_LANGS, i18n.language);

  const q = params.get("q") ?? "";
  const scope = (NEWS_SCOPES as readonly string[]).includes(params.get("scope") ?? "")
    ? (params.get("scope") as NewsScope)
    : "all";
  const sort = (NEWS_SORTS as readonly string[]).includes(params.get("sort") ?? "")
    ? (params.get("sort") as NewsSort)
    : "importance";
  const category = params.get("category");
  const country = params.get("country");
  const product = params.get("product");

  const isFiltered = Boolean(q || category || country || product) || scope !== "all";

  /*
   * The search box is the one control that does NOT read straight from the URL.
   * It has to stay responsive per keystroke while the URL updates on a pause, so
   * it owns its text and pushes it outward; the effect below is the only writer.
   */
  const [draftQ, setDraftQ] = useState(q);
  useEffect(() => {
    if (draftQ.trim() === q) return;
    const id = window.setTimeout(() => setFilter("q", draftQ.trim() || null), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
    // `setFilter` closes over `params`, and re-running on every param change
    // would re-fire the pending write after an unrelated filter moved.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftQ, q]);

  const filters: NewsFilterValues = {
    q: q || undefined,
    scope,
    sort,
    category: category || undefined,
    country: country || undefined,
    product: product || undefined,
    lang: i18n.language,
  };

  const articles = useNewsArticles(filters);
  const options = useNewsFilterOptions();

  const [filtersOpen, setFiltersOpen] = useState(false);

  const filterState: NewsFilterState = { category, country, product };

  /*
   * What the phone's filter button has to say for itself: behind a tap, a facet
   * the visitor set is otherwise invisible and the results just look short. `q`
   * and `scope` are excluded — both have their own visible control.
   */
  const activeFilterCount =
    (category ? 1 : 0) + (country ? 1 : 0) + (product ? 1 : 0);

  /** Write one filter into the URL. */
  function setFilter(key: string, value: string | null): void {
    const next = new URLSearchParams(params);
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: false });
  }

  function resetAll(): void {
    setDraftQ("");
    setParams(new URLSearchParams(), { replace: false });
  }

  return (
    <>
      <Seo
        title={t("news.metaTitle")}
        description={t("news.metaDescription")}
        canonical={canonical}
        alternates={isFiltered ? undefined : alternates}
        noindex={isFiltered}
      />

      {/*
        Phone toolbar. `PublicTopNav` is `sticky top-0 z-30` and 64px tall below
        `xl`, so `top-16` parks this immediately under it and the lower z-index
        keeps the header on top when they meet. Same bar as `/market` — the two
        pages have the same problem, so they get the same answer.
      */}
      <div className="sticky top-16 z-20 border-b border-border bg-bg/95 lg:hidden">
        <div className="mx-auto flex max-w-[1440px] items-center gap-2 px-4 py-2.5">
          <div className="relative min-w-0 flex-1">
            <label htmlFor="news-q-bar" className="sr-only">
              {t("news.search")}
            </label>
            <span
              aria-hidden
              className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-text-subtle"
            >
              <SearchIcon size={16} />
            </span>
            <input
              id="news-q-bar"
              type="search"
              value={draftQ}
              onChange={(e) => setDraftQ(e.target.value)}
              placeholder={t("news.searchPlaceholder")}
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
            {t("news.filters")}
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
          <h1 className="text-2xl font-semibold tracking-tight text-text">{t("news.title")}</h1>
          <p className="mt-1 text-sm text-text-muted">{t("news.subtitle")}</p>
        </header>

        <div className="mt-6 grid gap-8 lg:mt-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
          {/*
            Desktop rail. `lg:sticky`, not `sticky`: a grid item's sticky
            containing block is its grid AREA, and below `lg` this grid is one
            column, so the rail would pin over the results all the way down.
            `hidden` below `lg` because those widths get the sheet instead.
          */}
          <aside
            aria-label={t("news.filters")}
            className="hidden min-w-0 lg:sticky lg:top-6 lg:block lg:self-start"
          >
            <div className="mb-6">
              <label htmlFor="news-q" className="block text-xs font-medium text-text-muted">
                {t("news.search")}
              </label>
              <input
                id="news-q"
                type="search"
                value={draftQ}
                onChange={(e) => setDraftQ(e.target.value)}
                placeholder={t("news.searchPlaceholder")}
                className="mt-1.5 h-10 w-full rounded-md border border-border bg-surface-inset px-3 text-sm text-text placeholder:text-text-subtle focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              />
            </div>

            <NewsFilters
              idPrefix="news"
              state={filterState}
              options={options.data}
              loading={options.isLoading}
              onChange={setFilter}
            />

            {isFiltered ? (
              <button
                type="button"
                onClick={resetAll}
                className="mt-6 text-sm text-brand hover:underline"
              >
                {t("news.reset")}
              </button>
            ) : null}
          </aside>

          <div className="min-w-0">
            {/*
              Scope tabs. Real buttons in a `tablist`, not `<Tabs>`: that
              primitive owns tab-panel switching, and these four do not swap a
              panel — they re-query the one list below.
            */}
            <div
              role="tablist"
              aria-label={t("news.scopeLabel")}
              className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 lg:mx-0 lg:px-0"
            >
              {NEWS_SCOPES.map((s) => (
                <button
                  key={s}
                  type="button"
                  role="tab"
                  aria-selected={scope === s}
                  onClick={() => setFilter("scope", s === "all" ? null : s)}
                  className={
                    scope === s
                      ? "shrink-0 rounded-full border border-brand-line bg-brand-soft px-3.5 py-1.5 text-sm font-medium text-brand"
                      : "shrink-0 rounded-full border border-border px-3.5 py-1.5 text-sm font-medium text-text-muted transition-colors hover:border-brand-line hover:text-text"
                  }
                >
                  {t(`news.scope.${s}`)}
                </button>
              ))}
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
              <label htmlFor="news-sort" className="text-xs text-text-muted">
                {t("news.sort.label")}
              </label>
              <select
                id="news-sort"
                value={sort}
                onChange={(e) => setFilter("sort", e.target.value)}
                className="h-9 rounded-md border border-border bg-surface-inset px-2 text-sm text-text focus:border-brand-line focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {NEWS_SORTS.map((s) => (
                  <option key={s} value={s}>
                    {t(`news.sort.${s}`)}
                  </option>
                ))}
              </select>

              <div className="ms-auto text-sm text-text-muted" aria-live="polite">
                {articles.isLoading ? (
                  <Skeleton className="h-5 w-24" />
                ) : (
                  t("news.resultCount", { count: articles.data?.length ?? 0 })
                )}
              </div>
            </div>

            {articles.isLoading ? (
              <div className="mt-4 space-y-3">
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
              </div>
            ) : articles.isError ? (
              <div className="mt-4">
                <ErrorView
                  title={t("errors.loadFailed")}
                  retryLabel={t("common.retry")}
                  onRetry={() => void articles.refetch()}
                />
              </div>
            ) : articles.data && articles.data.length > 0 ? (
              <div className="mt-4 space-y-3">
                {articles.data.map((a) => (
                  <ArticleCard key={a.id} article={a} />
                ))}
              </div>
            ) : (
              <div className="mt-4">
                <EmptyState
                  icon={<NewspaperIcon size={28} />}
                  title={isFiltered ? t("news.noResults") : t("news.empty")}
                  description={isFiltered ? t("news.noResultsBody") : t("news.emptyBody")}
                  action={
                    isFiltered ? (
                      <button
                        type="button"
                        onClick={resetAll}
                        className={buttonClasses({ variant: "outline" })}
                      >
                        {t("news.reset")}
                      </button>
                    ) : undefined
                  }
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/*
        The rail, on demand. `placement="sheet"` is a `Dialog` variant rather
        than a new component precisely so this inherits the focus trap, Escape,
        body scroll lock, backdrop and focus restoration a hand-rolled drawer
        would have to re-earn.

        No «Применить» that applies anything: every control writes straight to
        the query string, so the list behind the sheet is already filtered and
        the primary button only has to dismiss. It states the count instead,
        which doubles as live feedback while the visitor is still choosing.
      */}
      <Dialog
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        placement="sheet"
        title={t("news.filters")}
        className="lg:hidden"
        footer={
          <>
            <button
              type="button"
              onClick={() => {
                resetAll();
                setFiltersOpen(false);
              }}
              className={buttonClasses({ variant: "outline", className: "!h-11 shrink-0 px-4" })}
            >
              {t("common.clear")}
            </button>
            <button
              type="button"
              onClick={() => setFiltersOpen(false)}
              className={buttonClasses({ fullWidth: true, className: "!h-11" })}
            >
              {articles.isLoading
                ? t("news.showResults")
                : t("news.resultCount", { count: articles.data?.length ?? 0 })}
            </button>
          </>
        }
      >
        <NewsFilters
          idPrefix="news-sheet"
          state={filterState}
          options={options.data}
          loading={options.isLoading}
          onChange={setFilter}
        />
      </Dialog>
    </>
  );
}
