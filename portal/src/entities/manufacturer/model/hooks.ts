import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import { manufacturerApi, manufacturerKeys } from "./api";
import type {
  FactoryRfq,
  FactoryRfqCreatePayload,
  ManufacturerThread,
} from "./types";

/** How often the manufacturer chat re-reads. Same cadence as the Trade Room. */
export const MANUFACTURER_CHAT_POLL_MS = 15_000;

/** Open (or fetch the existing) 1:1 thread with a manufacturer. */
/**
 * The 1:1 thread with a manufacturer, opening it if there is not one yet.
 *
 * A QUERY even though the endpoint POSTs. `POST /manufacturers/{id}/threads` is
 * get-or-create — calling it twice returns the same thread — so from the caller's
 * side this is a read, and modelling it as a read is what makes it correct.
 *
 * It was a mutation fired from an effect behind a `useRef` guard, and that hangs
 * the chat screen on a permanent spinner. Callbacks passed to `mutate()` are
 * dropped if the observer unsubscribes before the request settles, which is
 * exactly what React's StrictMode mount → cleanup → mount does in dev; the ref
 * then blocked the retry, so the thread was never stored and the page waited
 * forever. `useQuery` owns that lifecycle: it dedupes, survives the remount and
 * keeps the result in the cache rather than in component state.
 */
export function useManufacturerThread(
  manufacturerId: number | null,
  companyId: number | null,
): UseQueryResult<ManufacturerThread> {
  return useQuery<ManufacturerThread>({
    queryKey: manufacturerKeys.thread(manufacturerId, companyId),
    queryFn: () => manufacturerApi.openThread(manufacturerId as number, companyId as number),
    enabled: manufacturerId != null && companyId != null,
  });
}

export function useManufacturerThreads(companyId: number | null) {
  return useQuery<ManufacturerThread[]>({
    queryKey: manufacturerKeys.threads(companyId),
    queryFn: () => manufacturerApi.threads(companyId as number),
    enabled: companyId != null,
  });
}

export function useCreateFactoryRfq(manufacturerId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FactoryRfqCreatePayload) =>
      manufacturerApi.createRfq(manufacturerId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["manufacturers", "rfqs"] });
    },
  });
}

export function useFactoryRfq(rfqId: number | null, companyId: number | null) {
  return useQuery<FactoryRfq>({
    queryKey: manufacturerKeys.rfq(rfqId, companyId),
    queryFn: () => manufacturerApi.getRfq(rfqId as number, companyId as number),
    enabled: rfqId != null && companyId != null,
  });
}

export function useFactoryRfqs(companyId: number | null, side: "sent" | "incoming" = "sent") {
  return useQuery<FactoryRfq[]>({
    queryKey: manufacturerKeys.rfqs(companyId, side),
    queryFn: () => manufacturerApi.listRfqs(companyId as number, side),
    enabled: companyId != null,
  });
}
