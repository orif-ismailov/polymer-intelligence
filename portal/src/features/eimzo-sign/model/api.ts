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
    // Our own sidecar verifies the PKCS#7 and nothing else; `signature_hex` is
    // carried for Didox's benefit and simply unused here.
    verify: ({ pkcs7_64 }) =>
      eimzoApi
        .verify(companyId, pkcs7_64)
        .then((out) => ({ ok: out.ok, reason: out.reason, data: out })),
  };
}

// A `companyRegistrationSigner` used to live here — it created the company from
// the certificate's STIR so the wizard could sign before the row existed.
// Registration no longer involves E-IMZO at all (identity is established by
// documents and staff review), so the only signer left is the one below, used
// once the company is already there.
