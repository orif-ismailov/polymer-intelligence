import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { requestApi, requestKeys } from "./api";
import type { RequestDetail, RequestPayload, RequestSummary } from "./types";

export function useRequests(companyId: number | null) {
  return useQuery<RequestSummary[]>({
    queryKey: requestKeys.list(companyId ?? -1),
    queryFn: () => requestApi.list(companyId as number),
    enabled: companyId != null,
  });
}

export function useRequest(requestId: number | null, companyId: number | null) {
  return useQuery<RequestDetail>({
    queryKey: requestKeys.detail(requestId ?? -1, companyId ?? -1),
    queryFn: () => requestApi.get(requestId as number, companyId as number),
    enabled: requestId != null && companyId != null,
  });
}

export function useCreateRequest(companyId: number | null) {
  const qc = useQueryClient();
  return useMutation<RequestSummary, Error, RequestPayload>({
    mutationFn: (payload) => requestApi.create(payload),
    onSuccess: () => {
      if (companyId != null) void qc.invalidateQueries({ queryKey: requestKeys.list(companyId) });
    },
  });
}

export function useCancelRequest(companyId: number | null) {
  const qc = useQueryClient();
  return useMutation<RequestSummary, Error, number>({
    mutationFn: (requestId) => requestApi.cancel(requestId, companyId as number),
    onSuccess: (summary) => {
      if (companyId != null) {
        void qc.invalidateQueries({ queryKey: requestKeys.list(companyId) });
        void qc.invalidateQueries({ queryKey: requestKeys.detail(summary.id, companyId) });
      }
    },
  });
}
