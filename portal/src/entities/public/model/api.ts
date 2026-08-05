import { api } from "@/shared/api";

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
 * Calls against `/public`, the one API surface that answers without a session.
 *
 * Every function here runs in BOTH environments — the SSR render calls them with
 * no cookies, the browser calls them again on navigation. They must therefore
 * stay free of anything browser-only (no `window`, no `localStorage`); the fetch
 * client already handles the origin difference.
 */

const BASE = "/public";

/** Query keys, exported so the SSR entry can prefetch into the same cache. */
export const publicKeys = {
  offers: (filters: PublicOfferFilters, offset: number, limit: number) =>
    ["public", "offers", filters, offset, limit] as const,
  offer: (id: number) => ["public", "offer", id] as const,
  categories: (lang: string) => ["public", "categories", lang] as const,
  directory: (slug: string, q: string, country: string, offset: number, limit: number) =>
    ["public", "directory", slug, q, country, offset, limit] as const,
  company: (slug: string, id: number) => ["public", "company", slug, id] as const,
  stats: () => ["public", "stats"] as const,
  prices: (lang: string, limit: number) => ["public", "prices", lang, limit] as const,
  news: (lang: string, limit: number) => ["public", "news", lang, limit] as const,
};

export function fetchPublicOffers(
  filters: PublicOfferFilters,
  offset: number,
  limit: number,
): Promise<PublicOfferList> {
  return api.get<PublicOfferList>(`${BASE}/offers`, {
    query: { ...filters, offset, limit },
  });
}

export function fetchPublicOffer(offerId: number): Promise<PublicOfferDetail> {
  return api.get<PublicOfferDetail>(`${BASE}/offers/${offerId}`);
}

export function fetchPublicCategories(lang: string): Promise<PublicCategory[]> {
  return api.get<PublicCategory[]>(`${BASE}/categories`, { query: { lang } });
}

export function fetchPublicDirectory(
  slug: string,
  q: string,
  country: string,
  offset: number,
  limit: number,
): Promise<PublicCompanyList> {
  return api.get<PublicCompanyList>(`${BASE}/directories/${slug}`, {
    query: { q: q || undefined, country: country || undefined, offset, limit },
  });
}

export function fetchPublicCompany(
  slug: string,
  companyId: number,
): Promise<PublicCompanyDetail> {
  return api.get<PublicCompanyDetail>(`${BASE}/directories/${slug}/${companyId}`);
}

export function fetchPublicStats(): Promise<PublicStats> {
  return api.get<PublicStats>(`${BASE}/stats`);
}

export function fetchPublicPrices(lang: string, limit = 6): Promise<PublicQuote[]> {
  return api.get<PublicQuote[]>(`${BASE}/prices`, { query: { lang, limit } });
}

export function fetchPublicNews(lang: string, limit = 3): Promise<PublicNewsCard[]> {
  return api.get<PublicNewsCard[]>(`${BASE}/news`, { query: { lang, limit } });
}

/**
 * Image URL for a public offer photo.
 *
 * Points at the already-public webapp media proxy rather than a new route: those
 * bytes are served by the API for approved offers only, and duplicating the
 * endpoint would mean two places to get the approved-only gate right.
 */
export function publicOfferImageUrl(offerId: number, fileId: number): string {
  return `/api/v1/webapp/market/offers/${offerId}/images/${fileId}`;
}
