import { api } from "@/shared/api";

import type { NewsArticle, NewsArticleDetail, NewsFilters } from "./types";

export const newsApi = {
  list: (filters: NewsFilters, limit = 30): Promise<NewsArticle[]> =>
    api.get<NewsArticle[]>("/portal/news/articles", {
      query: {
        q: filters.q || undefined,
        scope: filters.scope || undefined,
        importance: filters.importance || undefined,
        lang: filters.lang || undefined,
        limit,
      },
    }),

  get: (signalId: number, lang?: string): Promise<NewsArticleDetail> =>
    api.get<NewsArticleDetail>(`/portal/news/articles/${signalId}`, {
      query: { lang: lang || undefined },
    }),
};

export const newsKeys = {
  list: (filters: NewsFilters) => ["news", filters] as const,
  detail: (signalId: number, lang?: string) => ["news", "detail", signalId, lang ?? ""] as const,
};
