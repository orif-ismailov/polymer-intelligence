import { useQuery } from "@tanstack/react-query";

import { marketApi, marketKeys } from "./api";
import type { MarketFilters, MarketOffer, MarketOfferDetail } from "./types";

/** Browse approved offers (excludes the active company's own when companyId set). */
export function useMarket(
  filters: MarketFilters,
  companyId: number | null,
  offset = 0,
) {
  return useQuery<MarketOffer[]>({
    queryKey: marketKeys.list(filters, companyId, offset),
    queryFn: () => marketApi.list(filters, { companyId, offset }),
  });
}

/** A single offer + the active company's inquiries on it. */
export function useMarketOffer(offerId: number | null, companyId: number | null) {
  return useQuery<MarketOfferDetail>({
    queryKey: marketKeys.detail(offerId ?? -1, companyId),
    queryFn: () => marketApi.get(offerId as number, companyId),
    enabled: offerId != null,
  });
}
