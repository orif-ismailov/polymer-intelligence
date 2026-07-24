import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { offerApi, offerKeys } from "./api";
import type { CompanyOffer } from "./types";

/** List offers for a company. */
export function useOffers(companyId: number | null) {
  return useQuery<CompanyOffer[]>({
    queryKey: offerKeys.list(companyId ?? -1),
    queryFn: () => offerApi.list(companyId as number),
    enabled: companyId != null,
  });
}

/** Fetch a single offer. */
export function useOffer(companyId: number | null, offerId: number | null) {
  return useQuery<CompanyOffer>({
    queryKey: offerKeys.detail(companyId ?? -1, offerId ?? -1),
    queryFn: () => offerApi.get(companyId as number, offerId as number),
    enabled: companyId != null && offerId != null,
  });
}

/** Archive an offer, then refresh the list. */
export function useArchiveOffer(companyId: number) {
  const qc = useQueryClient();
  return useMutation<CompanyOffer, Error, number>({
    mutationFn: (offerId) => offerApi.archive(companyId, offerId),
    onSuccess: (offer) => {
      qc.setQueryData(offerKeys.detail(companyId, offer.id), offer);
      void qc.invalidateQueries({ queryKey: offerKeys.list(companyId) });
    },
  });
}
