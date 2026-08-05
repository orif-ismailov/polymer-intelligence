import { api, resolveDownloadUrl } from "@/shared/api";

import type {
  BankAccount,
  CompanyDetail,
  CompanyProfilePatch,
  CompanySummary,
  CreateBankAccountPayload,
  CompanyReviewPayload,
  CompanyReviewResult,
  CreateCompanyPayload,
  DocumentMeta,
  PublicProfilePatch,
} from "./types";

export const companyApi = {
  list: (): Promise<CompanySummary[]> => api.get<CompanySummary[]>("/portal/companies"),

  get: (id: number): Promise<CompanyDetail> =>
    api.get<CompanyDetail>(`/portal/companies/${id}`),

  create: (payload: CreateCompanyPayload): Promise<CompanySummary> =>
    api.post<CompanySummary>("/portal/companies", payload),

  updateProfile: (id: number, patch: CompanyProfilePatch): Promise<CompanyDetail> =>
    api.patch<CompanyDetail>(`/portal/companies/${id}`, patch),

  /**
   * Storefront copy, and the only profile write a verified company can make —
   * `PATCH /portal/companies/{id}` is closed once verification decides.
   */
  updatePublicProfile: (id: number, patch: PublicProfilePatch): Promise<CompanyDetail> =>
    api.patch<CompanyDetail>(`/portal/companies/${id}/public-profile`, { logistics: patch }),

  uploadCover: (id: number, file: File): Promise<CompanyDetail> => {
    const form = new FormData();
    form.append("file", file);
    return api.post<CompanyDetail>(`/portal/companies/${id}/cover`, form);
  },

  deleteCover: (id: number): Promise<void> =>
    api.del<void>(`/portal/companies/${id}/cover`),

  /** Rate a counterparty. Re-submitting replaces the author's existing review. */
  submitReview: (
    companyId: number,
    payload: CompanyReviewPayload,
  ): Promise<CompanyReviewResult> =>
    api.post<CompanyReviewResult>(`/portal/companies/${companyId}/reviews`, payload),

  setRoles: (id: number, roles: string[]): Promise<CompanyDetail> =>
    api.put<CompanyDetail>(`/portal/companies/${id}/roles`, { roles }),

  addBankAccount: (id: number, payload: CreateBankAccountPayload): Promise<CompanyDetail> =>
    api.post<CompanyDetail>(`/portal/companies/${id}/bank-accounts`, payload),

  removeBankAccount: (id: number, accountId: number): Promise<CompanyDetail> =>
    api.del<CompanyDetail>(`/portal/companies/${id}/bank-accounts/${accountId}`),

  uploadDocument: (id: number, kind: string, file: File): Promise<DocumentMeta> => {
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    return api.upload<DocumentMeta>(`/portal/companies/${id}/documents`, form);
  },

  uploadLogo: (id: number, file: File): Promise<CompanyDetail> => {
    const form = new FormData();
    form.append("file", file);
    return api.upload<CompanyDetail>(`/portal/companies/${id}/logo`, form);
  },

  deleteLogo: (id: number): Promise<void> =>
    api.del<void>(`/portal/companies/${id}/logo`),

  removeDocument: (id: number, documentId: number): Promise<void> =>
    api.del<void>(`/portal/companies/${id}/documents/${documentId}`),

  documentDownloadUrl: (id: number, documentId: number): Promise<string> =>
    resolveDownloadUrl(`/portal/companies/${id}/documents/${documentId}/download`),
};

export type { BankAccount };

export const companyKeys = {
  all: ["companies"] as const,
  list: () => ["companies", "list"] as const,
  detail: (id: number) => ["companies", "detail", id] as const,
};
