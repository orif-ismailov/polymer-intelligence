import { api } from "@/shared/api";

import type { CaseOut } from "./types";

/** Verification case API. Scoped to a company via its numeric id. */
export const verificationApi = {
  get: (companyId: number): Promise<CaseOut> =>
    api.get<CaseOut>(`/portal/companies/${companyId}/verification`),

  submit: (companyId: number): Promise<CaseOut> =>
    api.post<CaseOut>(`/portal/companies/${companyId}/verification/submit`),
};

export const verificationKeys = {
  detail: (companyId: number) => ["verification", companyId] as const,
};
