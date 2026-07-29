import { useQuery } from "@tanstack/react-query";

import { newsApi, newsKeys } from "./api";
import type { NewsArticle, NewsArticleDetail, NewsFilters } from "./types";

export function useNewsArticles(filters: NewsFilters) {
  return useQuery<NewsArticle[]>({
    queryKey: newsKeys.list(filters),
    queryFn: () => newsApi.list(filters),
  });
}

export function useNewsArticle(signalId: number | null, lang?: string) {
  return useQuery<NewsArticleDetail>({
    queryKey: newsKeys.detail(signalId ?? -1, lang),
    queryFn: () => newsApi.get(signalId as number, lang),
    enabled: signalId != null,
  });
}
