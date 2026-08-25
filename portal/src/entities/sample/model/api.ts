import { api } from "@/shared/api";

import type {
  SampleLetter,
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

  /**
   * The letter's state. For the BUYER this also renders it if it does not exist
   * yet — which is why it is a plain read for the seller and the buyer's first
   * step, not a separate "create" call.
   */
  letter: (sampleId: number): Promise<SampleLetter> =>
    api.get<SampleLetter>(`/portal/samples/${sampleId}/letter`),

  /** Presigned PDF; `as=url` because an iframe cannot carry the Bearer token. */
  letterUrl: (sampleId: number): Promise<string> =>
    api
      .get<{ url: string }>(`/portal/samples/${sampleId}/letter/document`, {
        query: { as: "url" },
      })
      .then((r) => r.url),

  /** Single-use, bound to the letter's sha256 — a re-render invalidates it. */
  letterChallenge: (sampleId: number): Promise<string> =>
    api
      .post<{ challenge: string }>(`/portal/samples/${sampleId}/letter/challenge`)
      .then((r) => r.challenge),

  /** Signing is what releases the request to the seller. */
  signLetter: (sampleId: number, pkcs7: string): Promise<SampleRequest> =>
    api.post<SampleRequest>(`/portal/samples/${sampleId}/letter/sign`, { pkcs7 }),
};

export const sampleKeys = {
  list: (companyId: number, side: SampleSide) => ["samples", companyId, side] as const,
};
