import { api } from "@/shared/api";

import type {
  ContractDetail,
  ContractSummary,
  ContractTemplate,
  CreateContractPayload,
  DirectoryCompany,
  Specification,
  SpecificationList,
  SpecificationPayload,
  TermPreset,
  TermPresetList,
  TermPresetPayload,
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

  /**
   * Resolve one verified company by id — the exact door the product page needs to
   * preselect a seller. A name search would depend on the seller's legal name
   * matching the ilike, and a company trading under a short name never would.
   * Empty when the id is not (or no longer) verified.
   */
  directoryById: (companyId: number): Promise<DirectoryCompany[]> =>
    api.get<DirectoryCompany[]>("/portal/companies/directory", {
      query: { company_id: companyId },
    }),

  list: (params: ListParams = {}): Promise<ContractSummary[]> =>
    api.get<ContractSummary[]>("/portal/contracts", { query: { ...params } }),

  get: (id: number): Promise<ContractDetail> => api.get<ContractDetail>(`/portal/contracts/${id}`),

  create: (payload: CreateContractPayload): Promise<ContractDetail> =>
    api.post<ContractDetail>("/portal/contracts", payload),

  send: (id: number): Promise<ContractDetail> => api.post<ContractDetail>(`/portal/contracts/${id}/send`),
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

  termPresets: (companyId: number): Promise<TermPresetList> =>
    api.get<TermPresetList>(`/portal/companies/${companyId}/contract-term-presets`),
  createTermPreset: (companyId: number, payload: TermPresetPayload): Promise<TermPreset> =>
    api.post<TermPreset>(`/portal/companies/${companyId}/contract-term-presets`, payload),
  updateTermPreset: (
    companyId: number,
    presetId: number,
    payload: TermPresetPayload,
  ): Promise<TermPreset> =>
    api.put<TermPreset>(`/portal/companies/${companyId}/contract-term-presets/${presetId}`, payload),
  specifications: (contractId: number): Promise<SpecificationList> =>
    api.get<SpecificationList>(`/portal/contracts/${contractId}/specifications`),
  createSpecification: (contractId: number, variables: SpecificationPayload): Promise<Specification> =>
    api.post<Specification>(`/portal/contracts/${contractId}/specifications`, { variables }),
  cancelSpecification: (contractId: number, specId: number): Promise<Specification> =>
    api.post<Specification>(`/portal/contracts/${contractId}/specifications/${specId}/cancel`),
  /** Presigned PDF URL of a specification — for an <iframe> or a new tab. */
  specificationUrl: (contractId: number, specId: number): Promise<string> =>
    api
      .get<{ url: string }>(`/portal/contracts/${contractId}/specifications/${specId}/document`, {
        query: { as: "url" },
      })
      .then((r) => r.url),

  archiveTermPreset: (companyId: number, presetId: number): Promise<void> =>
    api.del<void>(`/portal/companies/${companyId}/contract-term-presets/${presetId}`),
};

export const contractKeys = {
  all: ["contracts"] as const,
  list: (params: ListParams = {}) => ["contracts", "list", params] as const,
  detail: (id: number) => ["contracts", "detail", id] as const,
  templates: () => ["contracts", "templates"] as const,
  termPresets: (companyId: number) => ["contracts", "term-presets", companyId] as const,
  specifications: (contractId: number) => ["contracts", "specifications", contractId] as const,
};
