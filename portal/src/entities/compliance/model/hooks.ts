import { useEffect, useState } from "react";

import { useMutation, useQuery } from "@tanstack/react-query";

import { complianceApi, complianceKeys } from "./api";
import type {
  CompanyLicense,
  OfferCompliance,
  SubstanceBrief,
  SubstanceSuggestion,
} from "./types";

/** Debounce a search term so a picker does not fire a request per keystroke. */
function useDebounced(value: string, delay = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Registry search for the offer form's picker. Two characters minimum. */
export function useSubstanceSearch(term: string) {
  const q = useDebounced(term.trim());
  return useQuery<SubstanceBrief[]>({
    queryKey: complianceKeys.substances(q),
    queryFn: () => complianceApi.searchSubstances(q),
    enabled: q.length >= 2,
  });
}

/** What this offer still needs before it can be published. */
export function useOfferCompliance(companyId: number | null, offerId: number | null) {
  return useQuery<OfferCompliance>({
    queryKey: complianceKeys.offer(companyId ?? -1, offerId ?? -1),
    queryFn: () => complianceApi.offerCompliance(companyId as number, offerId as number),
    enabled: companyId != null && offerId != null,
  });
}

/** Licences the company holds (registered by staff — read-only here). */
export function useCompanyLicenses(companyId: number | null) {
  return useQuery<CompanyLicense[]>({
    queryKey: complianceKeys.licenses(companyId ?? -1),
    queryFn: () => complianceApi.licenses(companyId as number),
    enabled: companyId != null,
  });
}

/** Ask for an AI hint. Resolves to null when there is none to give. */
export function useSuggestSubstance(companyId: number | null) {
  return useMutation<SubstanceSuggestion | null, Error, { text: string; offerId?: number | null }>({
    mutationFn: ({ text, offerId }) =>
      complianceApi.suggest(companyId as number, text, offerId ?? null),
  });
}

/** Record the seller's answer to a hint (both answers are journalled). */
export function useDecideSuggestion(companyId: number | null) {
  return useMutation<SubstanceSuggestion, Error, { suggestionId: number; accepted: boolean }>({
    mutationFn: ({ suggestionId, accepted }) =>
      complianceApi.decideSuggestion(companyId as number, suggestionId, accepted),
  });
}
