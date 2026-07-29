import type { CaseOut } from "@/entities/verification";
import { api } from "@/shared/api";

import type { EimzoSigner } from "./useEimzoSign";

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

/** Signer config for company-identity confirmation (wizard + verification status). */
export function companyIdentitySigner(companyId: number): EimzoSigner<EimzoVerifyOut> {
  return {
    getChallenge: () => eimzoApi.challenge(companyId).then((r) => r.challenge),
    verify: (pkcs7) =>
      eimzoApi
        .verify(companyId, pkcs7)
        .then((out) => ({ ok: out.ok, reason: out.reason, data: out })),
  };
}
