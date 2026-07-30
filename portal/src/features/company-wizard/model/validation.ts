import { BANK_MFO_LENGTH, UZ_TAX_ID_LENGTH } from "@/shared/config";

import { ALWAYS_REQUIRED_DOCS, isLaboratoryType, isLogisticsType, isManufacturerType } from "./constants";
import type {
  WizardBank,
  WizardDocuments,
  WizardIdentity,
  WizardLaboratoryProfile,
  WizardLogisticsProfile,
  WizardManufacturerProfile,
} from "./draftStore";
import { emptyLaboratory, emptyLogistics } from "./draftStore";

const DIGITS = /^\d+$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isTaxIdValid(identity: WizardIdentity): boolean {
  const value = identity.tax_id.trim();
  // Strict 9-digit rule applies to UZ; other jurisdictions accept any non-empty id.
  if (identity.jurisdiction === "UZ") {
    return value.length === UZ_TAX_ID_LENGTH && DIGITS.test(value);
  }
  return value.length > 0;
}

/**
 * Default «Основная информация» — every asterisked field from the shared mockup.
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

/**
 * Manufacturer legal step (companys_list.jpeg step 1): logo is optional;
 * commercial name optional; registration number + factory address required.
 * Ownership form / registration date are not on that sheet.
 */
export function isManufacturerIdentityValid(identity: WizardIdentity): boolean {
  return (
    isTaxIdValid(identity) &&
    identity.legal_name.trim().length > 0 &&
    identity.legal_address.trim().length > 0 &&
    identity.actual_address.trim().length > 0 &&
    identity.registration_number.trim().length > 0
  );
}

/**
 * Logistics legal step (logist_reg_flow.jpeg step 1): logo optional; city required;
 * ownership form / registration date are not on that sheet.
 */
export function isLogisticsIdentityValid(
  identity: WizardIdentity,
  logistics: WizardLogisticsProfile,
): boolean {
  return (
    isTaxIdValid(identity) &&
    identity.legal_name.trim().length > 0 &&
    identity.legal_address.trim().length > 0 &&
    logistics.city.trim().length > 0
  );
}

/**
 * Laboratory basic-info step (labaratory_reg_flow.jpeg «Основная информация»):
 * logo optional; city + description + email + phone required; ownership form /
 * registration date are not on that sheet. Website is optional.
 */
export function isLaboratoryIdentityValid(
  identity: WizardIdentity,
  laboratory: WizardLaboratoryProfile,
): boolean {
  return (
    isTaxIdValid(identity) &&
    identity.legal_name.trim().length > 0 &&
    identity.legal_address.trim().length > 0 &&
    laboratory.city.trim().length > 0 &&
    laboratory.description.trim().length > 0 &&
    EMAIL_RE.test(laboratory.email.trim()) &&
    laboratory.phone.trim().length > 0
  );
}

export function isIdentityValidForType(
  identity: WizardIdentity,
  accountType: string,
  logistics: WizardLogisticsProfile = emptyLogistics,
  laboratory: WizardLaboratoryProfile = emptyLaboratory,
): boolean {
  if (isManufacturerType(accountType)) return isManufacturerIdentityValid(identity);
  if (isLogisticsType(accountType)) return isLogisticsIdentityValid(identity, logistics);
  if (isLaboratoryType(accountType)) return isLaboratoryIdentityValid(identity, laboratory);
  return isIdentityValid(identity);
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

function isPositiveNumber(value: string): boolean {
  const n = Number(value);
  return value.trim().length > 0 && Number.isFinite(n) && n >= 0;
}

function isPositiveInt(value: string): boolean {
  return /^\d+$/.test(value.trim()) && Number(value) >= 0;
}

/** Production step — every asterisked field on the mockup. */
export function isProductionValid(profile: WizardManufacturerProfile): boolean {
  const exportOk =
    !profile.markets.includes("export") || profile.export_countries.length > 0;
  return (
    profile.production_type.trim().length > 0 &&
    profile.main_products.trim().length > 0 &&
    isPositiveNumber(profile.annual_capacity_tons) &&
    isPositiveInt(profile.production_lines) &&
    isPositiveInt(profile.employees) &&
    profile.markets.length > 0 &&
    exportOk &&
    /^\d{4}$/.test(profile.founded_year)
  );
}

/** Buyer-requirements step — only MOQ is required. */
export function isBuyerRequirementsValid(profile: WizardManufacturerProfile): boolean {
  return isPositiveNumber(profile.moq_tons);
}

export function isLogisticsServicesValid(profile: WizardLogisticsProfile): boolean {
  return profile.services.length > 0;
}

export function isLogisticsGeographyValid(profile: WizardLogisticsProfile): boolean {
  return profile.from_countries.length > 0 && profile.to_countries.length > 0;
}

export function isLogisticsSpecializationValid(profile: WizardLogisticsProfile): boolean {
  return profile.cargo_types.length > 0;
}

export function isLogisticsTariffsValid(profile: WizardLogisticsProfile): boolean {
  return profile.tariff_model.trim().length > 0;
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
export function requiredDocumentKinds(
  bank: WizardBank,
  identityLocked = false,
  accountType = "",
): string[] {
  if (isManufacturerType(accountType) || isLogisticsType(accountType) || isLaboratoryType(accountType)) {
    // Typed-flow certs are optional to advance; registration cert still required
    // when E-IMZO did not lock identity (documents_complete check).
    return identityLocked ? [] : [...ALWAYS_REQUIRED_DOCS];
  }
  const required = identityLocked ? [] : [...ALWAYS_REQUIRED_DOCS];
  if (bank.enabled) required.push("bank_letter");
  return required;
}

export function areDocumentsValid(
  documents: WizardDocuments,
  bank: WizardBank,
  identityLocked = false,
  accountType = "",
): boolean {
  return requiredDocumentKinds(bank, identityLocked, accountType).every(
    (kind) => documents[kind] instanceof File,
  );
}
