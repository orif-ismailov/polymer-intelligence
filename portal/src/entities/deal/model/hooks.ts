import { useQuery } from "@tanstack/react-query";

import { dealApi, dealKeys, rfqApi } from "./api";
import type { DealDetail, DealList, MarketRequest, RfqResponse } from "./types";

/** How often the Trade Room re-reads. SSE is out of scope for P2. */
export const DEAL_POLL_MS = 15_000;

export function useDeals(companyId: number | null, params: { role?: string; status?: string } = {}) {
  return useQuery<DealList>({
    queryKey: dealKeys.list(companyId, params),
    queryFn: () => dealApi.list(companyId as number, params),
    enabled: companyId != null,
  });
}

export function useDeal(companyId: number | null, dealId: number | null) {
  return useQuery<DealDetail>({
    queryKey: dealKeys.detail(companyId, dealId),
    queryFn: () => dealApi.get(companyId as number, dealId as number),
    enabled: companyId != null && dealId != null,
    // The counterparty's transitions arrive without us asking; the header and
    // action bar have to follow them.
    refetchInterval: DEAL_POLL_MS,
  });
}

export function useRfqResponses(companyId: number | null, requestId: number | null) {
  return useQuery<{ items: RfqResponse[] }>({
    queryKey: dealKeys.responses(companyId, requestId),
    queryFn: () => rfqApi.responses(companyId as number, requestId as number),
    enabled: companyId != null && requestId != null,
  });
}

export function useOpenRfqs(companyId: number | null) {
  return useQuery<{ items: MarketRequest[] }>({
    queryKey: dealKeys.openRequests(companyId),
    queryFn: () => rfqApi.openRequests(companyId as number),
    enabled: companyId != null,
  });
}
