import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import {
  fetchPublicCategories,
  fetchPublicCompany,
  fetchPublicDirectory,
  fetchPublicNews,
  fetchPublicOffer,
  fetchPublicOffers,
  fetchPublicPrices,
  fetchPublicStats,
  publicKeys,
} from "./api";
import type {
  PublicCategory,
  PublicCompanyDetail,
  PublicCompanyList,
  PublicNewsCard,
  PublicOfferDetail,
  PublicOfferFilters,
  PublicOfferList,
  PublicQuote,
  PublicStats,
} from "./types";

/**
 * Storefront read hooks.
 *
 * `staleTime` is deliberately generous. These queries were already resolved on
 * the server and shipped down as dehydrated state, so a refetch on mount would
 * throw away the work SSR just did and flash the same data in again. Catalog
 * content changes on the order of minutes, not seconds.
 */
const STALE = 5 * 60 * 1000;

export function usePublicOffers(
  filters: PublicOfferFilters,
  offset: number,
  limit: number,
): UseQueryResult<PublicOfferList> {
  return useQuery({
    queryKey: publicKeys.offers(filters, offset, limit),
    queryFn: () => fetchPublicOffers(filters, offset, limit),
    staleTime: STALE,
  });
}

export function usePublicOffer(offerId: number | null): UseQueryResult<PublicOfferDetail> {
  return useQuery({
    queryKey: publicKeys.offer(offerId ?? 0),
    queryFn: () => fetchPublicOffer(offerId as number),
    enabled: offerId != null,
    staleTime: STALE,
  });
}

export function usePublicCategories(): UseQueryResult<PublicCategory[]> {
  const { i18n } = useTranslation();
  const lang = i18n.language;
  return useQuery({
    queryKey: publicKeys.categories(lang),
    queryFn: () => fetchPublicCategories(lang),
    staleTime: STALE,
  });
}

export function usePublicDirectory(
  slug: string,
  q: string,
  country: string,
  offset: number,
  limit: number,
): UseQueryResult<PublicCompanyList> {
  return useQuery({
    queryKey: publicKeys.directory(slug, q, country, offset, limit),
    queryFn: () => fetchPublicDirectory(slug, q, country, offset, limit),
    staleTime: STALE,
  });
}

export function usePublicCompany(
  slug: string,
  companyId: number | null,
): UseQueryResult<PublicCompanyDetail> {
  return useQuery({
    queryKey: publicKeys.company(slug, companyId ?? 0),
    queryFn: () => fetchPublicCompany(slug, companyId as number),
    enabled: companyId != null,
    staleTime: STALE,
  });
}

export function usePublicStats(): UseQueryResult<PublicStats> {
  return useQuery({
    queryKey: publicKeys.stats(),
    queryFn: fetchPublicStats,
    staleTime: STALE,
  });
}

export function usePublicPrices(limit = 6): UseQueryResult<PublicQuote[]> {
  const { i18n } = useTranslation();
  const lang = i18n.language;
  return useQuery({
    queryKey: publicKeys.prices(lang, limit),
    queryFn: () => fetchPublicPrices(lang, limit),
    staleTime: STALE,
  });
}

export function usePublicNews(limit = 3): UseQueryResult<PublicNewsCard[]> {
  const { i18n } = useTranslation();
  const lang = i18n.language;
  return useQuery({
    queryKey: publicKeys.news(lang, limit),
    queryFn: () => fetchPublicNews(lang, limit),
    staleTime: STALE,
  });
}
