import { useQuery } from "@tanstack/react-query";

import { newsApi, newsKeys } from "./api";
import type {
  NewsArticle,
  NewsArticleDetail,
  NewsFilterOptions,
  NewsFilters,
} from "./types";

export function useNewsArticles(filters: NewsFilters) {
  return useQuery<NewsArticle[]>({
    queryKey: newsKeys.list(filters),
    queryFn: () => newsApi.list(filters),
  });
}

/**
 * The facet values behind the filter controls.
 *
 * `staleTime` because these describe a 30-day window and move on the ingest
 * cadence, not on interaction. Without it, every filter change would re-fetch
 * and re-render the controls the visitor is in the middle of using.
 */
export function useNewsFilterOptions(days?: number) {
  return useQuery<NewsFilterOptions>({
    queryKey: newsKeys.filters(days),
    queryFn: () => newsApi.filters(days),
    staleTime: 5 * 60 * 1000,
  });
}

export function useNewsArticle(signalId: number | null, lang?: string) {
  return useQuery<NewsArticleDetail>({
    queryKey: newsKeys.detail(signalId ?? -1, lang),
    queryFn: () => newsApi.get(signalId as number, lang),
    enabled: signalId != null,
  });
}
