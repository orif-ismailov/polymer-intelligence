import { BANK_MFO_LENGTH, UZ_TAX_ID_LENGTH } from "@/shared/config";

import { ALWAYS_REQUIRED_DOCS } from "./constants";
import type { WizardBank, WizardDocuments, WizardIdentity } from "./draftStore";

const DIGITS = /^\d+$/;

export function isTaxIdValid(identity: WizardIdentity): boolean {
  const value = identity.tax_id.trim();
  // Strict 9-digit rule applies to UZ; other jurisdictions accept any non-empty id.
  if (identity.jurisdiction === "UZ") {
    return value.length === UZ_TAX_ID_LENGTH && DIGITS.test(value);
  }
  return value.length > 0;
}

export function isIdentityValid(identity: WizardIdentity): boolean {
  return isTaxIdValid(identity);
}

export function isRolesValid(roles: string[]): boolean {
  return roles.length > 0;
}

export function isMfoValid(mfo: string): boolean {
  return mfo.length === BANK_MFO_LENGTH && DIGITS.test(mfo);
}

export function isBankValid(bank: WizardBank): boolean {
  if (!bank.enabled) return true; // skipped is valid
  return isMfoValid(bank.bank_mfo) && bank.account_number.trim().length > 0;
}

/** The set of document kinds required given current draft state. */
export function requiredDocumentKinds(bank: WizardBank): string[] {
  const required = [...ALWAYS_REQUIRED_DOCS];
  if (bank.enabled) required.push("bank_letter");
  return required;
}

export function areDocumentsValid(documents: WizardDocuments, bank: WizardBank): boolean {
  return requiredDocumentKinds(bank).every((kind) => documents[kind] instanceof File);
}
