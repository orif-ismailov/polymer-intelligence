import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/shared/api";

import { logisticsRequestApi, logisticsRequestKeys } from "./api";
import type { LogisticsRequest, LogisticsRequestCreatePayload } from "./types";

export function useCreateLogisticsRequest(logisticsId: number) {
  const queryClient = useQueryClient();
  // `ApiError` rather than the default `Error`: the server codes its refusals
  // in `detail.code`, and the form maps on that — with a bare `Error` the code
  // is invisible to the type system and every refusal reads as generic.
  return useMutation<LogisticsRequest, ApiError, LogisticsRequestCreatePayload>({
    mutationFn: (payload) => logisticsRequestApi.create(logisticsId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: logisticsRequestKeys.all });
    },
  });
}

export function useLogisticsRequest(requestId: number | null, companyId: number | null) {
  return useQuery<LogisticsRequest>({
    queryKey: logisticsRequestKeys.detail(requestId, companyId),
    queryFn: () => logisticsRequestApi.get(requestId as number, companyId as number),
    // Nullable ids rather than a boolean: the query must not fire from Node
    // during SSR, nor before the active company has settled.
    enabled: requestId != null && companyId != null,
  });
}

export function useLogisticsRequests(
  companyId: number | null,
  side: "sent" | "incoming" = "sent",
) {
  return useQuery<LogisticsRequest[]>({
    queryKey: logisticsRequestKeys.list(companyId, side),
    queryFn: () =>
      logisticsRequestApi.list(companyId as number, side).then((r) => r.items),
    enabled: companyId != null,
  });
}
