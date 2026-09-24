import { api } from "@/shared/api";

import type {
  CompanyOffer,
  TechFeedItem,
  TechOfferInput,
  TechRequest,
  TechRequestInput,
  TechMessage,
  TechReview,
  TechThread,
} from "./types";

const EXPERT = "/portal/me/technologist";
const company = (companyId: number) => `/portal/companies/${companyId}/tech-requests`;
const THREADS = "/portal/tech-threads";

interface Items<T> {
  items: T[];
}
interface MessagePage {
  items: TechMessage[];
  last_id: number | null;
}

export const techRequestKeys = {
  all: ["tech-requests"] as const,
  companyList: (companyId: number | null) => ["tech-requests", "company", companyId] as const,
  companyDetail: (companyId: number | null, id: number | null) =>
    ["tech-requests", "company", companyId, id] as const,
  offers: (companyId: number | null, id: number | null) =>
    ["tech-requests", "offers", companyId, id] as const,
  review: (companyId: number | null, id: number | null) =>
    ["tech-requests", "review", companyId, id] as const,
  feed: (invited: boolean) => ["tech-requests", "feed", invited] as const,
  feedItem: (id: number | null) => ["tech-requests", "feed-item", id] as const,
};

export const techRequestApi = {
  // ── the factory ──
  list: (companyId: number): Promise<Items<TechRequest>> =>
    api.get<Items<TechRequest>>(company(companyId)),
  create: (companyId: number, payload: TechRequestInput): Promise<TechRequest> =>
    api.post<TechRequest>(company(companyId), payload),
  get: (companyId: number, id: number): Promise<TechRequest> =>
    api.get<TechRequest>(`${company(companyId)}/${id}`),
  cancel: (companyId: number, id: number): Promise<TechRequest> =>
    api.post<TechRequest>(`${company(companyId)}/${id}/cancel`),
  offers: (companyId: number, id: number): Promise<Items<CompanyOffer>> =>
    api.get<Items<CompanyOffer>>(`${company(companyId)}/${id}/offers`),
  accept: (companyId: number, id: number, offerId: number): Promise<TechRequest> =>
    api.post<TechRequest>(`${company(companyId)}/${id}/offers/${offerId}/accept`),
  decline: (companyId: number, id: number, offerId: number): Promise<TechRequest> =>
    api.post<TechRequest>(`${company(companyId)}/${id}/offers/${offerId}/decline`),
  complete: (
    companyId: number,
    id: number,
    body: { rating: number; text: string | null },
  ): Promise<TechReview> => api.post<TechReview>(`${company(companyId)}/${id}/complete`, body),
  review: (companyId: number, id: number): Promise<TechReview | null> =>
    api.get<TechReview | null>(`${company(companyId)}/${id}/review`),
  invite: (companyId: number, id: number, profileId: number): Promise<void> =>
    api.post<void>(`${company(companyId)}/${id}/invites`, { profile_id: profileId }),
  openThreadAsCompany: (companyId: number, id: number, profileId: number): Promise<TechThread> =>
    api.post<TechThread>(`${company(companyId)}/${id}/threads/${profileId}`),

  // ── the expert ──
  feed: (invited: boolean): Promise<Items<TechFeedItem>> =>
    api.get<Items<TechFeedItem>>(`${EXPERT}/requests`, {
      query: { invited: invited || undefined },
    }),
  feedItem: (id: number): Promise<TechFeedItem> =>
    api.get<TechFeedItem>(`${EXPERT}/requests/${id}`),
  submitOffer: (id: number, payload: TechOfferInput): Promise<TechFeedItem> =>
    api.post<TechFeedItem>(`${EXPERT}/requests/${id}/offer`, payload),
  updateOffer: (id: number, payload: TechOfferInput): Promise<TechFeedItem> =>
    api.put<TechFeedItem>(`${EXPERT}/requests/${id}/offer`, payload),
  withdrawOffer: (id: number): Promise<TechFeedItem> =>
    api.del<TechFeedItem>(`${EXPERT}/requests/${id}/offer`),
  openThreadAsExpert: (id: number): Promise<TechThread> =>
    api.post<TechThread>(`${EXPERT}/requests/${id}/thread`),

  // ── threads, both sides. `companyId` null ⇒ reading as the expert. ──
  messages: (threadId: number, companyId: number | null, afterId?: number | null) =>
    api.get<MessagePage>(`${THREADS}/${threadId}/messages`, {
      query: { company_id: companyId ?? undefined, after_id: afterId ?? undefined },
    }),
  postMessage: (
    threadId: number,
    companyId: number | null,
    body: string,
    file?: File | null,
  ): Promise<TechMessage> => {
    const form = new FormData();
    if (companyId != null) form.append("company_id", String(companyId));
    form.append("body", body);
    if (file) form.append("file", file);
    return api.post<TechMessage>(`${THREADS}/${threadId}/messages`, form);
  },
  messageFileUrl: (threadId: number, messageId: number, companyId: number | null) =>
    api.get<{ url: string }>(`${THREADS}/${threadId}/messages/${messageId}/file`, {
      query: { company_id: companyId ?? undefined },
    }),
};

/**
 * The `ThreadChat` adapter for a tech thread. `ThreadChat` passes a company id
 * through to every call; here it is the SIDE: a real id reads as that factory,
 * `null` reads as the expert (the component's own `companyId` prop is then 0
 * and only used for the fallback "mine" rule, which `mine` from the server
 * overrides).
 */
export function techThreadChatApi(companyId: number | null) {
  return {
    messages: (threadId: number, _c: number, afterId?: number | null) =>
      techRequestApi.messages(threadId, companyId, afterId),
    postMessage: (threadId: number, _c: number, body: string, file?: File | null) =>
      techRequestApi.postMessage(threadId, companyId, body, file),
    messageFileUrl: (threadId: number, messageId: number) =>
      techRequestApi.messageFileUrl(threadId, messageId, companyId),
  };
}
