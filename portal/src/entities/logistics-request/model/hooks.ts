import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/shared/api";

import { logisticsRequestApi, logisticsRequestKeys } from "./api";
import type {
  LogisticsMessage,
  LogisticsPoolItem,
  LogisticsRequest,
  LogisticsRequestCreatePayload,
  LogisticsThread,
} from "./types";

/** Same cadence as the manufacturer and deal chats — one expectation of "live". */
export const LOGISTICS_CHAT_POLL_MS = 15_000;

export function useCreateLogisticsRequest() {
  const queryClient = useQueryClient();
  // `ApiError` rather than the default `Error`: the server codes its refusals in
  // `detail.code`, and with a bare `Error` that code is invisible to the type
  // system, so every refusal reads as generic.
  return useMutation<LogisticsRequest, ApiError, LogisticsRequestCreatePayload>({
    mutationFn: (payload) => logisticsRequestApi.create(payload),
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

/** The buyer's own requests. */
export function useLogisticsRequests(companyId: number | null) {
  return useQuery<LogisticsRequest[]>({
    queryKey: logisticsRequestKeys.list(companyId),
    queryFn: () => logisticsRequestApi.list(companyId as number).then((r) => r.items),
    enabled: companyId != null,
  });
}

/** The carrier pool. Empty (not an error) for a company that is not a carrier. */
export function useLogisticsPool(companyId: number | null) {
  return useQuery<LogisticsPoolItem[]>({
    queryKey: logisticsRequestKeys.pool(companyId),
    queryFn: () => logisticsRequestApi.pool(companyId as number).then((r) => r.items),
    enabled: companyId != null,
  });
}

/**
 * Get-or-create this carrier's thread on a request.
 *
 * A `useQuery` even though it POSTs, and that is load-bearing rather than
 * stylistic. `entities/manufacturer/model/hooks.ts` documents the failure the
 * obvious version has: a `mutate()` fired from an effect behind a `useRef`
 * guard hangs the screen on a permanent spinner, because callbacks passed to
 * `mutate()` are dropped when the observer unsubscribes before the request
 * settles — exactly what React StrictMode's mount → cleanup → mount does in dev
 * — and the ref then blocks the retry. `useQuery` owns that lifecycle.
 *
 * Safe to model this way because the endpoint is idempotent: it returns the
 * existing thread when there is one.
 */
export function useLogisticsThread(requestId: number | null, companyId: number | null) {
  return useQuery<LogisticsThread>({
    queryKey: logisticsRequestKeys.thread(requestId, companyId),
    queryFn: () =>
      logisticsRequestApi.openThread(requestId as number, companyId as number),
    enabled: requestId != null && companyId != null,
    staleTime: Infinity,
  });
}

export function useLogisticsThreads(companyId: number | null) {
  return useQuery<LogisticsThread[]>({
    queryKey: logisticsRequestKeys.threads(companyId),
    queryFn: () => logisticsRequestApi.threads(companyId as number).then((r) => r.items),
    enabled: companyId != null,
  });
}

export function usePostLogisticsMessage(threadId: number | null, companyId: number | null) {
  return useMutation<LogisticsMessage, ApiError, { body: string; file?: File | null }>({
    mutationFn: ({ body, file }) =>
      logisticsRequestApi.postMessage(
        threadId as number,
        companyId as number,
        body,
        file,
      ),
  });
}
