import { api } from "@/shared/api";

import type { LogisticsRequest, LogisticsRequestCreatePayload } from "./types";

const BASE = "/portal/logistics";

interface LogisticsRequestList {
  items: LogisticsRequest[];
}

export const logisticsRequestApi = {
  create: (
    logisticsId: number,
    payload: LogisticsRequestCreatePayload,
  ): Promise<LogisticsRequest> =>
    api.post<LogisticsRequest>(`${BASE}/${logisticsId}/requests`, payload),

  get: (requestId: number, companyId: number): Promise<LogisticsRequest> =>
    api.get<LogisticsRequest>(`${BASE}/requests/${requestId}`, {
      query: { company_id: companyId },
    }),

  list: (companyId: number, side: "sent" | "incoming"): Promise<LogisticsRequestList> =>
    api.get<LogisticsRequestList>(`${BASE}/requests`, {
      query: { company_id: companyId, side },
    }),
};

export const logisticsRequestKeys = {
  all: ["logistics-requests"] as const,
  list: (companyId: number | null, side: string) =>
    ["logistics-requests", "list", companyId, side] as const,
  detail: (requestId: number | null, companyId: number | null) =>
    ["logistics-requests", "detail", requestId, companyId] as const,
};
