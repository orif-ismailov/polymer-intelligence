import { useMutation, useQueryClient } from "@tanstack/react-query";

import { offerApi, offerKeys } from "@/entities/offer";
import type { CompanyOffer, OfferPayload } from "@/entities/offer";
import { ApiError } from "@/shared/api";

export function isNotVerifiedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403 && error.code === "company_not_verified";
}

interface SaveArgs {
  payload: OfferPayload;
}

/**
 * Create or update an offer. On success it primes the detail cache and
 * invalidates the list. The 403 `company_not_verified` is surfaced verbatim so
 * the caller can render the locked-state explainer.
 */
export function useSaveOffer(companyId: number, offerId: number | null) {
  const qc = useQueryClient();
  return useMutation<CompanyOffer, ApiError, SaveArgs>({
    mutationFn: ({ payload }) =>
      offerId == null
        ? offerApi.create(companyId, payload)
        : offerApi.update(companyId, offerId, payload),
    onSuccess: (offer) => {
      qc.setQueryData(offerKeys.detail(companyId, offer.id), offer);
      void qc.invalidateQueries({ queryKey: offerKeys.list(companyId) });
    },
  });
}
