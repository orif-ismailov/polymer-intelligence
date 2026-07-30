import { api } from "@/shared/api";

import type {
  FactoryRfq,
  FactoryRfqCreatePayload,
  FactoryRfqDocument,
  FactoryRfqDocumentKind,
  ManufacturerList,
  ManufacturerMessage,
  ManufacturerMessagePage,
  ManufacturerThread,
} from "./types";

const BASE = "/portal/manufacturers";

export const manufacturerApi = {
  // ── directory ──────────────────────────────────────────────────────────
  list: (
    params: { q?: string; limit?: number; offset?: number } = {},
  ): Promise<ManufacturerList> =>
    api.get<ManufacturerList>(BASE, {
      query: {
        q: params.q || undefined,
        limit: params.limit ?? 24,
        offset: params.offset ?? 0,
      },
    }),

  // ── chat ───────────────────────────────────────────────────────────────
  openThread: (manufacturerId: number, companyId: number): Promise<ManufacturerThread> =>
    api.post<ManufacturerThread>(`${BASE}/${manufacturerId}/threads`, {
      company_id: companyId,
    }),

  threads: (companyId: number): Promise<ManufacturerThread[]> =>
    api.get<ManufacturerThread[]>(`${BASE}/threads`, { query: { company_id: companyId } }),

  messages: (
    threadId: number,
    companyId: number,
    afterId?: number | null,
  ): Promise<ManufacturerMessagePage> =>
    api.get<ManufacturerMessagePage>(`${BASE}/threads/${threadId}/messages`, {
      query: { company_id: companyId, after_id: afterId ?? undefined },
    }),

  /** Multipart always, so a text-only and a file message take one code path. */
  postMessage: (
    threadId: number,
    companyId: number,
    body: string,
    file?: File | null,
  ): Promise<ManufacturerMessage> => {
    const form = new FormData();
    form.append("company_id", String(companyId));
    form.append("body", body);
    if (file) form.append("file", file);
    return api.upload<ManufacturerMessage>(`${BASE}/threads/${threadId}/messages`, form);
  },

  messageFileUrl: (threadId: number, messageId: number, companyId: number): Promise<string> =>
    api
      .get<{ url: string }>(`${BASE}/threads/${threadId}/messages/${messageId}/file`, {
        query: { company_id: companyId },
      })
      .then((r) => r.url),

  // ── factory RFQ ────────────────────────────────────────────────────────
  createRfq: (manufacturerId: number, payload: FactoryRfqCreatePayload): Promise<FactoryRfq> =>
    api.post<FactoryRfq>(`${BASE}/${manufacturerId}/rfqs`, payload),

  uploadRfqDocument: (
    rfqId: number,
    companyId: number,
    kind: FactoryRfqDocumentKind,
    file: File,
  ): Promise<FactoryRfqDocument> => {
    const form = new FormData();
    form.append("company_id", String(companyId));
    form.append("kind", kind);
    form.append("file", file);
    return api.upload<FactoryRfqDocument>(`${BASE}/rfqs/${rfqId}/documents`, form);
  },

  getRfq: (rfqId: number, companyId: number): Promise<FactoryRfq> =>
    api.get<FactoryRfq>(`${BASE}/rfqs/${rfqId}`, { query: { company_id: companyId } }),

  listRfqs: (companyId: number, side: "sent" | "incoming" = "sent"): Promise<FactoryRfq[]> =>
    api.get<FactoryRfq[]>(`${BASE}/rfqs`, { query: { company_id: companyId, side } }),
};

export const manufacturerKeys = {
  list: (q: string, offset: number) => ["manufacturers", "list", q, offset] as const,
  threads: (companyId: number | null) => ["manufacturers", "threads", companyId] as const,
  messages: (threadId: number | null, companyId: number | null) =>
    ["manufacturers", "messages", threadId, companyId] as const,
  rfq: (rfqId: number | null, companyId: number | null) =>
    ["manufacturers", "rfq", rfqId, companyId] as const,
  rfqs: (companyId: number | null, side: string) =>
    ["manufacturers", "rfqs", companyId, side] as const,
};
