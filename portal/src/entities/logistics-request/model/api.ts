import { api } from "@/shared/api";

import type {
  LogisticsMessage,
  LogisticsPoolItem,
  LogisticsRequest,
  LogisticsRequestCreatePayload,
  LogisticsThread,
} from "./types";

const BASE = "/portal/logistics";

interface RequestList {
  items: LogisticsRequest[];
}
interface PoolList {
  items: LogisticsPoolItem[];
}
interface ThreadList {
  items: LogisticsThread[];
}
interface MessagePage {
  items: LogisticsMessage[];
  last_id: number | null;
}

export const logisticsRequestApi = {
  /** Broadcast — no carrier is chosen anywhere in the flow. */
  create: (payload: LogisticsRequestCreatePayload): Promise<LogisticsRequest> =>
    api.post<LogisticsRequest>(`${BASE}/requests`, payload),

  get: (requestId: number, companyId: number): Promise<LogisticsRequest> =>
    api.get<LogisticsRequest>(`${BASE}/requests/${requestId}`, {
      query: { company_id: companyId },
    }),

  /** The buyer's own requests. The carrier side is `pool`. */
  list: (companyId: number): Promise<RequestList> =>
    api.get<RequestList>(`${BASE}/requests`, { query: { company_id: companyId } }),

  pool: (companyId: number): Promise<PoolList> =>
    api.get<PoolList>(`${BASE}/pool`, { query: { company_id: companyId } }),

  openThread: (requestId: number, companyId: number): Promise<LogisticsThread> =>
    api.post<LogisticsThread>(`${BASE}/requests/${requestId}/threads`, {
      company_id: companyId,
    }),

  threads: (companyId: number): Promise<ThreadList> =>
    api.get<ThreadList>(`${BASE}/threads`, { query: { company_id: companyId } }),

  messages: (
    threadId: number,
    companyId: number,
    afterId?: number | null,
  ): Promise<MessagePage> =>
    api.get<MessagePage>(`${BASE}/threads/${threadId}/messages`, {
      query: { company_id: companyId, after_id: afterId ?? undefined },
    }),

  postMessage: (
    threadId: number,
    companyId: number,
    body: string,
    file?: File | null,
  ): Promise<LogisticsMessage> => {
    const form = new FormData();
    form.append("company_id", String(companyId));
    form.append("body", body);
    if (file) form.append("file", file);
    return api.post<LogisticsMessage>(`${BASE}/threads/${threadId}/messages`, form);
  },

  messageFileUrl: (
    threadId: number,
    messageId: number,
    companyId: number,
  ): Promise<{ url: string }> =>
    api.get<{ url: string }>(
      `${BASE}/threads/${threadId}/messages/${messageId}/file`,
      { query: { company_id: companyId } },
    ),
};

export const logisticsRequestKeys = {
  all: ["logistics-requests"] as const,
  list: (companyId: number | null) => ["logistics-requests", "list", companyId] as const,
  pool: (companyId: number | null) => ["logistics-requests", "pool", companyId] as const,
  detail: (requestId: number | null, companyId: number | null) =>
    ["logistics-requests", "detail", requestId, companyId] as const,
  thread: (requestId: number | null, companyId: number | null) =>
    ["logistics-requests", "thread", requestId, companyId] as const,
  threads: (companyId: number | null) =>
    ["logistics-requests", "threads", companyId] as const,
};
