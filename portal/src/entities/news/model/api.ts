import { api } from "@/shared/api";

import type {
  NewsArticle,
  NewsArticleDetail,
  NewsFilterOptions,
  NewsFilters,
} from "./types";

/**
 * `/public/news/articles`, not `/portal/news/articles`.
 *
 * `/news` is a public, server-rendered, indexable URL — it has to render for a
 * crawler and for a signed-out visitor, and the portal twin of these endpoints
 * depends on `get_current_account`, which answers both of them 401. The public
 * routes run the same `news_service` calls behind the same response models
 * (pinned by a parity test); the only thing they drop is the session.
 */
const BASE = "/public/news/articles";

export const newsApi = {
  list: (filters: NewsFilters, limit = 30): Promise<NewsArticle[]> =>
    api.get<NewsArticle[]>(BASE, {
      query: {
        q: filters.q || undefined,
        // `all` is sent verbatim — the backend is what maps it to "no scope".
        scope: filters.scope || undefined,
        sort: filters.sort || undefined,
        category: filters.category || undefined,
        country: filters.country || undefined,
        company: filters.company || undefined,
        product: filters.product || undefined,
        importance: filters.importance || undefined,
        lang: filters.lang || undefined,
        days: filters.days || undefined,
        limit,
      },
    }),

  filters: (days?: number): Promise<NewsFilterOptions> =>
    api.get<NewsFilterOptions>(`${BASE}/filters`, {
      query: { days: days || undefined },
    }),

  get: (signalId: number, lang?: string): Promise<NewsArticleDetail> =>
    api.get<NewsArticleDetail>(`${BASE}/${signalId}`, {
      query: { lang: lang || undefined },
    }),
};

export const newsKeys = {
  list: (filters: NewsFilters) => ["news", filters] as const,
  // Its own key rather than part of the list key: the facets are identical for
  // every filter combination, so hanging them off the list would refetch the
  // whole control surface on each keystroke and each tab.
  filters: (days?: number) => ["news", "filters", days ?? 0] as const,
  detail: (signalId: number, lang?: string) => ["news", "detail", signalId, lang ?? ""] as const,
};
