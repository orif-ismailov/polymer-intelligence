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

/**
 * Every field on «Основная информация» carries a red asterisk in the mockup, so
 * the step gates on all of them — not just the tax id as it did when the screen
 * was a two-field identity form.
 */
export function isIdentityValid(identity: WizardIdentity): boolean {
  return (
    isTaxIdValid(identity) &&
    identity.legal_name.trim().length > 0 &&
    identity.legal_address.trim().length > 0 &&
    identity.legal_form.trim().length > 0 &&
    isRegistrationDateValid(identity.registration_date)
  );
}

/** A registration date must be a real past-or-today calendar date. */
export function isRegistrationDateValid(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return false;
  // Round-trip guards against calendar-invalid input (`2020-02-31` → 02 Mar).
  if (parsed.toISOString().slice(0, 10) !== value) return false;
  return parsed.getTime() <= Date.now();
}

export function isAccountTypeValid(accountType: string): boolean {
  return accountType.trim().length > 0;
}

export function isMfoValid(mfo: string): boolean {
  return mfo.length === BANK_MFO_LENGTH && DIGITS.test(mfo);
}

export function isBankValid(bank: WizardBank): boolean {
  if (!bank.enabled) return true; // skipped is valid
  return isMfoValid(bank.bank_mfo) && bank.account_number.trim().length > 0;
}

/**
 * The set of document kinds required given current draft state.
 *
 * `identityLocked` means an E-IMZO signature already proved who this company is.
 * The backend agrees and waives the paperwork — its `documents_complete` check
 * reports `{"required": [], "eimzo_passed": true}` for a signed company — so
 * demanding a registration certificate here blocked people who had just presented
 * a stronger proof than the document would have been.
 */
export function requiredDocumentKinds(bank: WizardBank, identityLocked = false): string[] {
  const required = identityLocked ? [] : [...ALWAYS_REQUIRED_DOCS];
  if (bank.enabled) required.push("bank_letter");
  return required;
}

export function areDocumentsValid(
  documents: WizardDocuments,
  bank: WizardBank,
  identityLocked = false,
): boolean {
  return requiredDocumentKinds(bank, identityLocked).every(
    (kind) => documents[kind] instanceof File,
  );
}
