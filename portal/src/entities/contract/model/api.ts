import { api } from "@/shared/api";

import type {
  ContractDetail,
  ContractSummary,
  ContractTemplate,
  CreateContractPayload,
  DirectoryCompany,
} from "./types";

interface ListParams {
  company_id?: number;
  role?: "initiator" | "counterparty";
  status?: string;
}

export const contractApi = {
  templates: (): Promise<ContractTemplate[]> =>
    api.get<ContractTemplate[]>("/portal/contract-templates"),

  directory: (q: string): Promise<DirectoryCompany[]> =>
    api.get<DirectoryCompany[]>("/portal/companies/directory", { query: { q } }),

  list: (params: ListParams = {}): Promise<ContractSummary[]> =>
    api.get<ContractSummary[]>("/portal/contracts", { query: { ...params } }),

  get: (id: number): Promise<ContractDetail> => api.get<ContractDetail>(`/portal/contracts/${id}`),

  create: (payload: CreateContractPayload): Promise<ContractDetail> =>
    api.post<ContractDetail>("/portal/contracts", payload),

  send: (id: number): Promise<ContractDetail> => api.post<ContractDetail>(`/portal/contracts/${id}/send`),
  accept: (id: number): Promise<ContractDetail> => api.post<ContractDetail>(`/portal/contracts/${id}/accept`),
  decline: (id: number, reason: string): Promise<ContractDetail> =>
    api.post<ContractDetail>(`/portal/contracts/${id}/decline`, { reason }),
  cancel: (id: number): Promise<ContractDetail> => api.post<ContractDetail>(`/portal/contracts/${id}/cancel`),

  signChallenge: (id: number): Promise<{ challenge: string }> =>
    api.post<{ challenge: string }>(`/portal/contracts/${id}/sign/challenge`),
  sign: (id: number, pkcs7: string): Promise<ContractDetail> =>
    api.post<ContractDetail>(`/portal/contracts/${id}/sign`, { pkcs7 }),

  /** Presigned PDF URL (S3, no auth needed) — safe for an <iframe> or window.open. */
  documentUrl: (id: number): Promise<string> =>
    api.get<{ url: string }>(`/portal/contracts/${id}/document`, { query: { as: "url" } }).then((r) => r.url),
  /** The signed bundle is a dynamic zip — fetch it authenticated as a Blob. */
  bundleBlob: (id: number): Promise<Blob> => api.blob(`/portal/contracts/${id}/bundle`),
};

export const contractKeys = {
  all: ["contracts"] as const,
  list: (params: ListParams = {}) => ["contracts", "list", params] as const,
  detail: (id: number) => ["contracts", "detail", id] as const,
  templates: () => ["contracts", "templates"] as const,
};
