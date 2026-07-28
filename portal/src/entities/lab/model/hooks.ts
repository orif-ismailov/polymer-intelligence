import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { labApi, labKeys } from "./api";
import type { LabOrder, LabOrderPayload } from "./types";

/** Every analysis this company has asked for, newest first. */
export function useLabOrders(companyId: number | null) {
  return useQuery<LabOrder[]>({
    queryKey: labKeys.list(companyId ?? -1),
    queryFn: () => labApi.list(companyId as number),
    enabled: companyId != null,
  });
}

/**
 * Raise a request for an analysis.
 *
 * Invalidates the offer list too: the offer form shows the order's status inside
 * its laboratory block, so a fresh request has to appear there without a reload.
 */
export function useCreateLabOrder(companyId: number | null) {
  const queryClient = useQueryClient();
  return useMutation<LabOrder, Error, LabOrderPayload>({
    mutationFn: (payload) => labApi.create(companyId as number, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: labKeys.list(companyId ?? -1) });
      void queryClient.invalidateQueries({ queryKey: ["offers", companyId] });
    },
  });
}
