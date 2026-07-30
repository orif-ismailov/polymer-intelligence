import { api } from "@/shared/api";

import type { Inquiry, InquiryPayload } from "./types";

export const inquiryApi = {
  /** Send an inquiry against an offer (buyer acts as a company). */
  create: (offerId: number, payload: InquiryPayload): Promise<Inquiry> =>
    api.post<Inquiry>(`/portal/market/${offerId}/inquiries`, payload),

  /** Inquiries my company has sent. */
  listSent: (companyId: number): Promise<Inquiry[]> =>
    api.get<Inquiry[]>("/portal/inquiries", { query: { company_id: companyId } }),

  /** Approved inquiries received on my company's offers. */
  listIncoming: (companyId: number): Promise<Inquiry[]> =>
    api.get<Inquiry[]>("/portal/inquiries/incoming", { query: { company_id: companyId } }),

  get: (inquiryId: number): Promise<Inquiry> =>
    api.get<Inquiry>(`/portal/inquiries/${inquiryId}`),

  /** Revise a sent inquiry (re-enters moderation). */
  update: (
    inquiryId: number,
    payload: InquiryPayload,
  ): Promise<Inquiry> => api.patch<Inquiry>(`/portal/inquiries/${inquiryId}`, payload),
};

export const inquiryKeys = {
  sent: (companyId: number) => ["inquiries", "sent", companyId] as const,
  incoming: (companyId: number) => ["inquiries", "incoming", companyId] as const,
  detail: (inquiryId: number) => ["inquiries", "detail", inquiryId] as const,
};
