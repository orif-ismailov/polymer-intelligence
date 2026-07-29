import { api } from "@/shared/api";

import type { RequestDetail, RequestPayload, RequestSummary } from "./types";

export const requestApi = {
  create: (payload: RequestPayload): Promise<RequestSummary> =>
    api.post<RequestSummary>("/portal/requests", payload),

  list: (companyId: number): Promise<RequestSummary[]> =>
    api.get<RequestSummary[]>("/portal/requests", { query: { company_id: companyId } }),

  get: (requestId: number, companyId: number): Promise<RequestDetail> =>
    api.get<RequestDetail>(`/portal/requests/${requestId}`, {
      query: { company_id: companyId },
    }),

  cancel: (requestId: number, companyId: number): Promise<RequestSummary> =>
    api.post<RequestSummary>(`/portal/requests/${requestId}/cancel`, undefined, {
      query: { company_id: companyId },
    }),

  uploadFile: (requestId: number, companyId: number, file: File): Promise<RequestFileResponse> => {
    const form = new FormData();
    form.append("company_id", String(companyId));
    form.append("file", file);
    return api.upload<RequestFileResponse>(`/portal/requests/${requestId}/files`, form);
  },
};

interface RequestFileResponse {
  id: number;
  file_name: string;
}

export const requestKeys = {
  list: (companyId: number) => ["requests", companyId] as const,
  detail: (requestId: number, companyId: number) =>
    ["requests", "detail", requestId, companyId] as const,
};
