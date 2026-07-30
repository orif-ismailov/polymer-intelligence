import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { marketApi, marketKeys } from "./api";
import type { MarketFilters, MarketOffer, MarketOfferDetail } from "./types";

/** Every market cache holds either a page of cards or one detail sheet. */
type MarketCache = MarketOffer[] | MarketOfferDetail | undefined;

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

/** Catalog-safe public profile of a verified seller company. */
export function usePublicCompanyProfile(companyId: number | null) {
  return useQuery({
    queryKey: marketKeys.companyProfile(companyId ?? -1),
    queryFn: () => marketApi.companyProfile(companyId as number),
    enabled: companyId != null,
  });
}

/** The account's own shortlist (not scoped to the active company). */
export function useFavorites() {
  return useQuery<MarketOffer[]>({
    queryKey: marketKeys.favorites(),
    queryFn: () => marketApi.favorites(),
  });
}

/**
 * Star/unstar an offer.
 *
 * Optimistic: the heart is the kind of control that must respond to the tap, not
 * to the network. On failure the previous cache is restored, and every market
 * query is invalidated on settle so the server stays the source of truth.
 *
 * Both cache shapes are patched. Listing only the array case left the product
 * detail — a single object under `["market","detail",…]` — untouched, so the one
 * screen with two hearts on it was the one where neither responded to the tap.
 */
export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, next }: { offerId: number; next: boolean }) =>
      next ? marketApi.star(offerId).then(() => undefined) : marketApi.unstar(offerId),
    onMutate: async ({ offerId, next }) => {
      await queryClient.cancelQueries({ queryKey: ["market"] });
      const snapshot = queryClient.getQueriesData<MarketCache>({ queryKey: ["market"] });
      queryClient.setQueriesData<MarketCache>({ queryKey: ["market"] }, (old) => {
        if (Array.isArray(old)) {
          return old.map((o) => (o.id === offerId ? { ...o, is_favorite: next } : o));
        }
        if (old && old.id === offerId) return { ...old, is_favorite: next };
        return old;
      });
      return { snapshot };
    },
    onError: (_err, _vars, context) => {
      context?.snapshot.forEach(([key, data]) => queryClient.setQueryData(key, data));
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["market"] });
    },
  });
}
