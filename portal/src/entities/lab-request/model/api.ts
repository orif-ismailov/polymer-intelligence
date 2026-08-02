import { api } from "@/shared/api";
import type { ThreadMessage } from "@/features/thread-chat";

import type {
  LabPoolItem,
  LabRequest,
  LabRequestCreatePayload,
  LabThread,
} from "./types";

const BASE = "/portal/lab";

export const labRequestApi = {
  /** Broadcast — no laboratory is chosen anywhere in the flow. */
  create: (payload: LabRequestCreatePayload): Promise<LabRequest> =>
    api.post<LabRequest>(`${BASE}/requests`, payload),

  get: (requestId: number, companyId: number): Promise<LabRequest> =>
    api.get<LabRequest>(`${BASE}/requests/${requestId}`, {
      query: { company_id: companyId },
    }),

  /** The buyer's own requests. The laboratory side is `pool`. */
  list: (companyId: number): Promise<{ items: LabRequest[] }> =>
    api.get<{ items: LabRequest[] }>(`${BASE}/requests`, {
      query: { company_id: companyId },
    }),

  pool: (companyId: number): Promise<{ items: LabPoolItem[] }> =>
    api.get<{ items: LabPoolItem[] }>(`${BASE}/pool`, {
      query: { company_id: companyId },
    }),

  openThread: (requestId: number, companyId: number): Promise<LabThread> =>
    api.post<LabThread>(`${BASE}/requests/${requestId}/threads`, {
      company_id: companyId,
    }),

  threads: (companyId: number): Promise<{ items: LabThread[] }> =>
    api.get<{ items: LabThread[] }>(`${BASE}/threads`, {
      query: { company_id: companyId },
    }),

  // ── The `ThreadChat` contract ────────────────────────────────────────────
  messages: (
    threadId: number,
    companyId: number,
    afterId?: number | null,
  ): Promise<{ items: ThreadMessage[]; last_id: number | null }> =>
    api.get<{ items: ThreadMessage[]; last_id: number | null }>(
      `${BASE}/threads/${threadId}/messages`,
      { query: { company_id: companyId, after_id: afterId ?? undefined } },
    ),

  postMessage: (
    threadId: number,
    companyId: number,
    body: string,
    file?: File | null,
  ): Promise<ThreadMessage> => {
    const form = new FormData();
    form.append("company_id", String(companyId));
    form.append("body", body);
    if (file) form.append("file", file);
    return api.post<ThreadMessage>(`${BASE}/threads/${threadId}/messages`, form);
  },

  messageFileUrl: (
    threadId: number,
    messageId: number,
    companyId: number,
  ): Promise<{ url: string }> =>
    api.get<{ url: string }>(`${BASE}/threads/${threadId}/messages/${messageId}/file`, {
      query: { company_id: companyId },
    }),
};

export const labRequestKeys = {
  all: ["lab-requests"] as const,
  list: (companyId: number | null) => ["lab-requests", "list", companyId] as const,
  pool: (companyId: number | null) => ["lab-requests", "pool", companyId] as const,
  detail: (requestId: number | null, companyId: number | null) =>
    ["lab-requests", "detail", requestId, companyId] as const,
  threads: (companyId: number | null) => ["lab-requests", "threads", companyId] as const,
};
