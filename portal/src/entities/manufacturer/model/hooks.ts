import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { manufacturerApi, manufacturerKeys } from "./api";
import type {
  FactoryRfq,
  FactoryRfqCreatePayload,
  ManufacturerList,
  ManufacturerThread,
} from "./types";

/** How often the manufacturer chat re-reads. Same cadence as the Trade Room. */
export const MANUFACTURER_CHAT_POLL_MS = 15_000;

export function useManufacturers(q: string, offset = 0, limit = 24) {
  return useQuery<ManufacturerList>({
    queryKey: manufacturerKeys.list(q, offset),
    queryFn: () => manufacturerApi.list({ q: q || undefined, offset, limit }),
  });
}

/** Open (or fetch the existing) 1:1 thread with a manufacturer. */
export function useOpenManufacturerThread() {
  return useMutation({
    mutationFn: ({
      manufacturerId,
      companyId,
    }: {
      manufacturerId: number;
      companyId: number;
    }) => manufacturerApi.openThread(manufacturerId, companyId),
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
