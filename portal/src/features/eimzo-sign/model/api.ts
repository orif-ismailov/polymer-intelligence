import type { CaseOut } from "@/entities/verification";
import { api } from "@/shared/api";

export interface EimzoVerifyOut {
  ok: boolean;
  reason: string | null;
  holder_masked: string | null;
  case: CaseOut;
}

export const eimzoApi = {
  challenge: (companyId: number): Promise<{ challenge: string }> =>
    api.post<{ challenge: string }>(`/portal/companies/${companyId}/eimzo/challenge`),

  verify: (companyId: number, pkcs7: string): Promise<EimzoVerifyOut> =>
    api.post<EimzoVerifyOut>(`/portal/companies/${companyId}/eimzo/verify`, { pkcs7 }),
};
