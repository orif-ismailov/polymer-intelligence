import { api } from "@/shared/api";

import type { CompanyOffer, OfferPayload } from "./types";

export const offerApi = {
  list: (companyId: number): Promise<CompanyOffer[]> =>
    api.get<CompanyOffer[]>(`/portal/companies/${companyId}/offers`),

  get: (companyId: number, offerId: number): Promise<CompanyOffer> =>
    api.get<CompanyOffer>(`/portal/companies/${companyId}/offers/${offerId}`),

  create: (companyId: number, payload: OfferPayload): Promise<CompanyOffer> =>
    api.post<CompanyOffer>(`/portal/companies/${companyId}/offers`, payload),

  update: (companyId: number, offerId: number, payload: OfferPayload): Promise<CompanyOffer> =>
    api.patch<CompanyOffer>(`/portal/companies/${companyId}/offers/${offerId}`, payload),

  archive: (companyId: number, offerId: number): Promise<CompanyOffer> =>
    api.post<CompanyOffer>(`/portal/companies/${companyId}/offers/${offerId}/archive`),

  uploadFile: (
    companyId: number,
    offerId: number,
    file: File,
    kind = "image",
  ): Promise<CompanyOffer> => {
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    return api.upload<CompanyOffer>(`/portal/companies/${companyId}/offers/${offerId}/files`, form);
  },

  deleteFile: (companyId: number, offerId: number, fileId: number): Promise<CompanyOffer> =>
    api.del<CompanyOffer>(
      `/portal/companies/${companyId}/offers/${offerId}/files/${fileId}`,
    ),

  /**
   * Photo bytes for one of the company's OWN offers, at any status.
   *
   * Fetched as a Blob rather than pointed at by `<img src>`: the access token lives
   * in memory only, so a bare img request carries no Authorization header and 401s.
   * The public catalog image URL can't stand in here either — it only serves files
   * of *approved* offers, and this is exactly the draft-preview case.
   */
  fileBlob: (companyId: number, offerId: number, fileId: number): Promise<Blob> =>
    api.blob(`/portal/companies/${companyId}/offers/${offerId}/files/${fileId}`),
};

export const offerKeys = {
  list: (companyId: number) => ["offers", companyId] as const,
  detail: (companyId: number, offerId: number) => ["offers", companyId, offerId] as const,
};
