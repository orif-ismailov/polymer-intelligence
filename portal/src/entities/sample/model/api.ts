import { api } from "@/shared/api";

import type {
  SampleRequest,
  SampleRequestPayload,
  SampleSide,
  SampleTransitionPayload,
} from "./types";

export const sampleApi = {
  list: (companyId: number, side: SampleSide): Promise<SampleRequest[]> =>
    api.get<SampleRequest[]>(`/portal/companies/${companyId}/samples`, {
      query: { side },
    }),

  request: (offerId: number, payload: SampleRequestPayload): Promise<SampleRequest> =>
    api.post<SampleRequest>(`/portal/market/offers/${offerId}/samples`, payload),

  /**
   * One door for every move. Which party may make it is the server's call
   * (`sample_service._ACTOR_RULES`), and `available_transitions` on the row says
   * what this side may press.
   */
  transition: (sampleId: number, payload: SampleTransitionPayload): Promise<SampleRequest> =>
    api.post<SampleRequest>(`/portal/samples/${sampleId}/transition`, payload),
};

export const sampleKeys = {
  list: (companyId: number, side: SampleSide) => ["samples", companyId, side] as const,
};
