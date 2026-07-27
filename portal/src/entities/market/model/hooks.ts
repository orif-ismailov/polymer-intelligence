import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
 */
export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, next }: { offerId: number; next: boolean }) =>
      next ? marketApi.star(offerId).then(() => undefined) : marketApi.unstar(offerId),
    onMutate: async ({ offerId, next }) => {
      await queryClient.cancelQueries({ queryKey: ["market"] });
      const snapshot = queryClient.getQueriesData<MarketOffer[]>({ queryKey: ["market"] });
      queryClient.setQueriesData<MarketOffer[]>({ queryKey: ["market"] }, (old) =>
        Array.isArray(old)
          ? old.map((o) => (o.id === offerId ? { ...o, is_favorite: next } : o))
          : old,
      );
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
