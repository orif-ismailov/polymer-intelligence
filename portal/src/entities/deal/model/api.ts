import { api } from "@/shared/api";

import type {
  DealDetail,
  DealDocument,
  DealDocumentKind,
  DealList,
  DealMessage,
  DealMessagePage,
  DealStatus,
  MarketRequest,
  MyRfqResponse,
  RfqResponse,
  RfqResponsePayload,
} from "./types";

const base = (companyId: number) => `/portal/companies/${companyId}/deals`;

export const dealApi = {
  /**
   * Contract variables the deal can already answer (product, quantity, price…).
   *
   * Best-effort: whatever it cannot answer is simply absent. `templateId` lets the
   * server drop values that would violate that template's enums rather than
   * failing validation on a field the user never touched.
   */
  contractPrefill: (
    companyId: number,
    dealId: number,
    templateId: number,
  ): Promise<Record<string, string>> =>
    api.get<Record<string, string>>(
      `/portal/companies/${companyId}/deals/${dealId}/contract-prefill?template_id=${templateId}`,
    ),

  list: (companyId: number, params: { role?: string; status?: string } = {}): Promise<DealList> =>
    api.get<DealList>(base(companyId), { query: { ...params } }),

  get: (companyId: number, dealId: number): Promise<DealDetail> =>
    api.get<DealDetail>(`${base(companyId)}/${dealId}`),

  transition: (
    companyId: number,
    dealId: number,
    toStatus: DealStatus,
    reason?: string,
  ): Promise<DealDetail> =>
    api.post<DealDetail>(`${base(companyId)}/${dealId}/transition`, {
      to_status: toStatus,
      reason: reason ?? null,
    }),

  // ── chat ────────────────────────────────────────────────────────────────
  messages: (companyId: number, dealId: number, afterId?: number | null): Promise<DealMessagePage> =>
    api.get<DealMessagePage>(`${base(companyId)}/${dealId}/messages`, {
      query: { after_id: afterId ?? undefined },
    }),

  /** Multipart always, so a text-only and a file message take one code path. */
  postMessage: (
    companyId: number,
    dealId: number,
    body: string,
    file?: File | null,
  ): Promise<DealMessage> => {
    const form = new FormData();
    form.append("body", body);
    if (file) form.append("file", file);
    return api.upload<DealMessage>(`${base(companyId)}/${dealId}/messages`, form);
  },

  messageFileUrl: (companyId: number, dealId: number, messageId: number): Promise<string> =>
    api
      .get<{ url: string }>(`${base(companyId)}/${dealId}/messages/${messageId}/file`, {
        query: { as: "url" },
      })
      .then((r) => r.url),

  // ── documents ───────────────────────────────────────────────────────────
  addDocument: (
    companyId: number,
    dealId: number,
    kind: DealDocumentKind,
    file: File,
  ): Promise<DealDocument> => {
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    return api.upload<DealDocument>(`${base(companyId)}/${dealId}/documents`, form);
  },

  /** Presigned S3 URL (no auth needed) — safe for window.open. */
  documentUrl: (companyId: number, dealId: number, documentId: number): Promise<string> =>
    api
      .get<{ url: string }>(`${base(companyId)}/${dealId}/documents/${documentId}`, {
        query: { as: "url" },
      })
      .then((r) => r.url),

  revokeDocument: (
    companyId: number,
    dealId: number,
    documentId: number,
    reason: string,
  ): Promise<DealDocument> =>
    api.post<DealDocument>(`${base(companyId)}/${dealId}/documents/${documentId}/revoke`, {
      reason,
    }),
};

export const rfqApi = {
  responses: (companyId: number, requestId: number): Promise<{ items: RfqResponse[] }> =>
    api.get<{ items: RfqResponse[] }>(
      `/portal/companies/${companyId}/requests/${requestId}/responses`,
    ),

  respond: (
    companyId: number,
    requestId: number,
    payload: RfqResponsePayload,
  ): Promise<RfqResponse> =>
    api.post<RfqResponse>(
      `/portal/companies/${companyId}/requests/${requestId}/responses`,
      payload,
    ),

  accept: (companyId: number, requestId: number, responseId: number): Promise<DealDetail> =>
    api.post<DealDetail>(
      `/portal/companies/${companyId}/requests/${requestId}/responses/${responseId}/accept`,
    ),

  withdraw: (companyId: number, requestId: number, responseId: number): Promise<RfqResponse> =>
    api.post<RfqResponse>(
      `/portal/companies/${companyId}/requests/${requestId}/responses/${responseId}/withdraw`,
    ),

  openRequests: (companyId: number): Promise<{ items: MarketRequest[] }> =>
    api.get<{ items: MarketRequest[] }>("/portal/market/requests", {
      query: { company_id: companyId },
    }),

  /** Every quote this company filed — the companion to `openRequests`, which
      drops a tender (and with it our own work) as soon as it closes. */
  myResponses: (companyId: number): Promise<{ items: MyRfqResponse[] }> =>
    api.get<{ items: MyRfqResponse[] }>("/portal/market/responses", {
      query: { company_id: companyId },
    }),
};

export const dealKeys = {
  all: ["deals"] as const,
  list: (companyId: number | null, params: Record<string, unknown> = {}) =>
    ["deals", "list", companyId, params] as const,
  detail: (companyId: number | null, id: number | null) =>
    ["deals", "detail", companyId, id] as const,
  messages: (companyId: number | null, id: number | null) =>
    ["deals", "messages", companyId, id] as const,
  responses: (companyId: number | null, requestId: number | null) =>
    ["rfq", "responses", companyId, requestId] as const,
  openRequests: (companyId: number | null) => ["rfq", "open", companyId] as const,
  myResponses: (companyId: number | null) => ["rfq", "mine", companyId] as const,
};
