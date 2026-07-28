import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sampleApi, sampleKeys } from "./api";
import type {
  SampleRequest,
  SampleRequestPayload,
  SampleSide,
  SampleTransitionPayload,
} from "./types";

/** `incoming` — requests to answer; `sent` — requests we made. */
export function useSamples(companyId: number | null, side: SampleSide) {
  return useQuery<SampleRequest[]>({
    queryKey: sampleKeys.list(companyId ?? -1, side),
    queryFn: () => sampleApi.list(companyId as number, side),
    enabled: companyId != null,
  });
}

export function useRequestSample(offerId: number | null) {
  const queryClient = useQueryClient();
  return useMutation<SampleRequest, Error, SampleRequestPayload>({
    mutationFn: (payload) => sampleApi.request(offerId as number, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["samples"] });
      // The offer page shows "you already asked", so its detail is stale too.
      void queryClient.invalidateQueries({ queryKey: ["market"] });
    },
  });
}

export function useTransitionSample() {
  const queryClient = useQueryClient();
  return useMutation<
    SampleRequest,
    Error,
    { sampleId: number } & SampleTransitionPayload
  >({
    mutationFn: ({ sampleId, ...payload }) => sampleApi.transition(sampleId, payload),
    // Both tabs can hold the same request from opposite sides, so refresh all.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["samples"] });
    },
  });
}
