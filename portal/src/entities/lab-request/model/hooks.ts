import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/shared/api";

import { labRequestApi, labRequestKeys } from "./api";
import type {
  LabPoolItem,
  LabRequest,
  LabRequestCreatePayload,
  LabThread,
} from "./types";

/** Same cadence as every other thread chat — one expectation of "live". */
export const LAB_CHAT_POLL_MS = 15_000;

export function useCreateLabRequest() {
  const queryClient = useQueryClient();
  // `ApiError`, not the default `Error`: the server codes its refusals in
  // `detail.code`, and a bare `Error` hides that from the type system.
  return useMutation<LabRequest, ApiError, LabRequestCreatePayload>({
    mutationFn: (payload) => labRequestApi.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: labRequestKeys.all });
    },
  });
}

export function useLabRequest(requestId: number | null, companyId: number | null) {
  return useQuery<LabRequest>({
    queryKey: labRequestKeys.detail(requestId, companyId),
    queryFn: () => labRequestApi.get(requestId as number, companyId as number),
    // Nullable ids, not a boolean: the query must not fire from Node during SSR
    // nor before the active company has settled.
    enabled: requestId != null && companyId != null,
  });
}

/** The buyer's own requests. */
export function useLabRequests(companyId: number | null) {
  return useQuery<LabRequest[]>({
    queryKey: labRequestKeys.list(companyId),
    queryFn: () => labRequestApi.list(companyId as number).then((r) => r.items),
    enabled: companyId != null,
  });
}

/** The pool. Empty (not an error) for a company that is not a laboratory. */
export function useLabPool(companyId: number | null) {
  return useQuery<LabPoolItem[]>({
    queryKey: labRequestKeys.pool(companyId),
    queryFn: () => labRequestApi.pool(companyId as number).then((r) => r.items),
    enabled: companyId != null,
  });
}

export function useLabThreads(companyId: number | null) {
  return useQuery<LabThread[]>({
    queryKey: labRequestKeys.threads(companyId),
    queryFn: () => labRequestApi.threads(companyId as number).then((r) => r.items),
    enabled: companyId != null,
  });
}
