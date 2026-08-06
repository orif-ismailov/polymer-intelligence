/**
 * One reporting source for a (possibly cross-source-merged) article.
 *
 * Mirrors the backend `NewsSourceRef`, which is `{id, name, published_at}` — it
 * carries no `url`. The link to the original lives on the article itself
 * (`NewsArticleDetail.source_url`), because only the representative source has one.
 */
export interface NewsSourceRef {
  id: number;
  name?: string | null;
  published_at?: string | null;
}

/** A classified news article card — mirror of the backend NewsArticleCard. */
export interface NewsArticle {
  id: number;
  headline: string;
  category: string | null;
  importance: string | null;
  market_impact: string | null;
  summary: string | null;
  analysis: string | null;
  recommendation: string | null;
  language: string | null;
  country: string | null;
  countries: string[];
  companies: string[];
  related_products: string[];
  source_name: string | null;
  published_at: string | null;
  image_url: string | null;
  sources: NewsSourceRef[];
  merged_count: number;
}

/** Full article (NewsArticleDetail) — adds original body + source link. */
export interface NewsArticleDetail extends NewsArticle {
  body: string | null;
  source_url: string | null;
}

/** The three directions the reader renders. */
export type MarketImpact = "positive" | "negative" | "neutral";

/**
 * Two vocabularies reach this field, so normalize before rendering.
 *
 * `parsing/news_schemas.NewsMarketImpact` is `positive | negative | neutral`,
 * but the classified rows in the database also carry `bullish` / `bearish` — the
 * response model types this as a bare `str`, not the enum, so nothing on the way
 * out rejects them. The Mini App maps only the enum spelling and silently drops
 * its arrow on every `bullish` article; this returns `null` only for a value
 * that really is unknown.
 */
export function normalizeMarketImpact(value: string | null): MarketImpact | null {
  switch (value) {
    case "positive":
    case "bullish":
      return "positive";
    case "negative":
    case "bearish":
      return "negative";
    case "neutral":
      return "neutral";
    default:
      return null;
  }
}

/**
 * The tab strip above the list. `all` is the tab's name for "no scope at all" —
 * the backend maps it back to `None` rather than treating it as a fourth scope,
 * so it must be sent as `all` and never omitted-but-meant.
 */
export const NEWS_SCOPES = ["all", "uzbekistan", "global", "producers"] as const;
export type NewsScope = (typeof NEWS_SCOPES)[number];

/** List order. `importance` (importance→recency) is the backend's default. */
export const NEWS_SORTS = [
  "importance",
  "newest",
  "category",
  "products",
  "country",
  "company",
] as const;
export type NewsSort = (typeof NEWS_SORTS)[number];

export interface NewsFilters {
  q?: string;
  scope?: NewsScope;
  sort?: NewsSort;
  category?: string;
  country?: string;
  company?: string;
  product?: string;
  importance?: string;
  lang?: string;
  days?: number;
}

/** One filterable value and how many recent articles carry it. */
export interface NewsFacet {
  value: string;
  count: number;
}

/**
 * Live facets — only values present in recent news, so the controls can never
 * offer a filter that returns nothing.
 *
 * `companies` is served and the `company` filter works, but the reader surfaces
 * category / country / product only, as the Mini App does: the company facet is
 * long, sparse and mostly one-article values, which makes it a scroll rather
 * than a filter.
 */
export interface NewsFilterOptions {
  categories: NewsFacet[];
  countries: NewsFacet[];
  companies: NewsFacet[];
  products: NewsFacet[];
}
