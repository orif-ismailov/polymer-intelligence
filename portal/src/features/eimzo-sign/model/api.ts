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

  verify: (
    companyId: number,
    pkcs7: string,
    signatureHex: string,
  ): Promise<EimzoVerifyOut> =>
    api.post<EimzoVerifyOut>(`/portal/companies/${companyId}/eimzo/verify`, {
      pkcs7,
      signature_hex: signatureHex,
    }),
};

/**
 * Signer config for company-identity confirmation (verification status page).
 *
 * **What gets signed is the INN, not the challenge.** Verification moved off our
 * own sidecar onto Didox, which authenticates a signature *for a given taxId* —
 * so the INN is the only payload it will accept, and a signature over our nonce
 * would simply be refused.
 *
 * The challenge round-trip stays, and it is not vestigial: the server mints it
 * per (company, account) and consumes it on verify, which is what stops a verify
 * being replayed against US. It is just no longer the thing inside the envelope,
 * so we fetch it and deliberately drop it.
 */
export function companyIdentitySigner(
  companyId: number,
  taxId: string,
): EimzoSigner<EimzoVerifyOut> {
  return {
    getChallenge: () => eimzoApi.challenge(companyId).then(() => taxId),
    // Both halves now: Didox's `/v1/dsvs/timestamp` takes the PKCS#7 AND the raw
    // signature, and refuses a bare envelope.
    verify: ({ pkcs7_64, signature_hex }) =>
      eimzoApi
        .verify(companyId, pkcs7_64, signature_hex)
        .then((out) => ({ ok: out.ok, reason: out.reason, data: out })),
  };
}

// A `companyRegistrationSigner` used to live here — it created the company from
// the certificate's STIR so the wizard could sign before the row existed.
// Registration no longer involves E-IMZO at all (identity is established by
// documents and staff review), so the only signer left is the one below, used
// once the company is already there.
