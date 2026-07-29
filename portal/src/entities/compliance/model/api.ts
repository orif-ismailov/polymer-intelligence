import { api } from "@/shared/api";

import type {
  CompanyLicense,
  OfferCompliance,
  SubstanceBrief,
  SubstanceSuggestion,
} from "./types";

export const complianceApi = {
  /** Registry search for the offer form's picker (empty term → []). */
  searchSubstances: (q: string): Promise<SubstanceBrief[]> =>
    api.get<SubstanceBrief[]>("/portal/substances", { query: { q } }),

  offerCompliance: (companyId: number, offerId: number): Promise<OfferCompliance> =>
    api.get<OfferCompliance>(`/portal/companies/${companyId}/offers/${offerId}/compliance`),

  licenses: (companyId: number): Promise<CompanyLicense[]> =>
    api.get<CompanyLicense[]>(`/portal/companies/${companyId}/licenses`),

  /**
   * Ask for an AI hint. Resolves to null on 204 — "no hint right now" (feature
   * off, or the daily token budget is spent) is not an error the seller can act
   * on, and picking the substance by hand always works.
   */
  suggest: (
    companyId: number,
    text: string,
    offerId?: number | null,
  ): Promise<SubstanceSuggestion | null> =>
    api
      .post<SubstanceSuggestion | null>(
        `/portal/companies/${companyId}/substance-suggestions`,
        { text, offer_id: offerId ?? null },
      )
      // A 204 comes back as undefined from the client; normalize so callers can
      // branch on one value.
      .then((row) => row ?? null),

  decideSuggestion: (
    companyId: number,
    suggestionId: number,
    accepted: boolean,
  ): Promise<SubstanceSuggestion> =>
    api.post<SubstanceSuggestion>(
      `/portal/companies/${companyId}/substance-suggestions/${suggestionId}/decision`,
      { accepted },
    ),
};

export const complianceKeys = {
  substances: (q: string) => ["substances", q] as const,
  offer: (companyId: number, offerId: number) => ["compliance", companyId, offerId] as const,
  licenses: (companyId: number) => ["licenses", companyId] as const,
};
