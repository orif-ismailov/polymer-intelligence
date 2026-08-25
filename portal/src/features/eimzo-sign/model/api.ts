import { companyApi } from "@/entities/company";
import type { CaseOut } from "@/entities/verification";
import { api } from "@/shared/api";

import { CertificateHasNoTin } from "./useEimzoSign";
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

/** A signature that also produced the company row it is attached to. */
export interface EimzoRegistration extends EimzoVerifyOut {
  company_id: number;
}

/**
 * Signer for a company that does not exist yet — registration step 1.
 *
 * The challenge endpoint is company-scoped, so the row has to exist before the
 * first round-trip. The certificate subject carries the organisation's STIR, so
 * the flow is: pick a certificate → create the company from its TIN → sign. That
 * is also why signing is offered *before* «Основная информация»: it fills the
 * requisites in rather than asking the user to retype what the key already says.
 *
 * `onCompany` fires as soon as the row exists, so a signature that fails partway
 * still leaves the wizard pointing at the created company instead of trying to
 * create it a second time (which would 409 on the unique tax id).
 */
export function companyRegistrationSigner(
  jurisdiction: string,
  onCompany: (companyId: number) => void,
): EimzoSigner<EimzoRegistration> {
  let companyId: number | null = null;

  return {
    getChallenge: async (cert) => {
      const tin = cert.tin?.trim();
      if (!tin) throw new CertificateHasNoTin();
      if (companyId == null) {
        const created = await companyApi.create({ jurisdiction, tax_id: tin });
        companyId = created.id;
        onCompany(created.id);
      }
      const { challenge } = await eimzoApi.challenge(companyId);
      return challenge;
    },
    verify: async ({ pkcs7_64 }) => {
      if (companyId == null) throw new Error("eimzo_no_company");
      const out = await eimzoApi.verify(companyId, pkcs7_64);
      return { ok: out.ok, reason: out.reason, data: { ...out, company_id: companyId } };
    },
  };
}
