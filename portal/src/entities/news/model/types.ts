export interface NewsSourceRef {
  name?: string | null;
  url?: string | null;
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

export interface NewsFilters {
  q?: string;
  scope?: string;
  importance?: string;
  lang?: string;
}
