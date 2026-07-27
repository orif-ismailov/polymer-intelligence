import { api } from "@/shared/api";
import { API_BASE } from "@/shared/config";

import type { MarketFilters, MarketOffer, MarketOfferDetail, OfferFileRef } from "./types";

export const marketApi = {
  list: (
    filters: MarketFilters,
    opts: { companyId?: number | null; limit?: number; offset?: number } = {},
  ): Promise<MarketOffer[]> =>
    api.get<MarketOffer[]>("/portal/market", {
      query: {
        q: filters.q || undefined,
        product_id: filters.product_id,
        availability: filters.availability,
        country: filters.country || undefined,
        company_id: opts.companyId ?? undefined,
        limit: opts.limit ?? 24,
        offset: opts.offset ?? 0,
      },
    }),

  get: (offerId: number, companyId?: number | null): Promise<MarketOfferDetail> =>
    api.get<MarketOfferDetail>(`/portal/market/${offerId}`, {
      query: { company_id: companyId ?? undefined },
    }),
};

export const marketKeys = {
  list: (filters: MarketFilters, companyId: number | null, offset: number) =>
    ["market", filters, companyId, offset] as const,
  detail: (offerId: number, companyId: number | null) =>
    ["market", "detail", offerId, companyId] as const,
};

/** Public <img src> URL for an offer file (the webapp image endpoint is public). */
export function offerImageUrl(offerId: number, fileId: number): string {
  return `${API_BASE}/webapp/market/offers/${offerId}/images/${fileId}`;
}

/**
 * Photos of a catalog offer in display order (upload order, cover first).
 *
 * Derived here rather than served as a `cover_file_id` field: the catalog card shape
 * is byte-parity-pinned with the Mini App by a backend contract test, so adding a
 * field to it would break that pin for no gain.
 */
export function offerPhotos(files: readonly OfferFileRef[]): OfferFileRef[] {
  return files.filter((f) => f.kind === "image");
}
