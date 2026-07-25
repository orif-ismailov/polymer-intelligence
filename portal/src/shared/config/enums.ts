/**
 * Domain enums mirrored verbatim from the backend contract.
 *
 * These are the authoritative option sets for chips, selects and labels. Keep
 * the string values byte-for-byte identical to the backend — translation labels
 * are resolved separately through i18n keys keyed by these values.
 */

export const COMPANY_STATUSES = [
  "draft",
  "pending_verification",
  "verified",
  "rejected",
  "suspended",
  "liquidated",
] as const;
export type CompanyStatus = (typeof COMPANY_STATUSES)[number];

export const CASE_STATUSES = [
  "draft",
  "submitted",
  "checks_running",
  "needs_info",
  "pending_review",
  "approved",
  "rejected",
  "cancelled",
] as const;
export type CaseStatus = (typeof CASE_STATUSES)[number];

export const CHECK_TYPES = [
  "tax_id_format",
  "bank_requisites",
  "documents_complete",
  "manual_kyb",
  "eimzo_signature",
] as const;
export type CheckType = (typeof CHECK_TYPES)[number];

export const CHECK_STATUSES = [
  "pending",
  "running",
  "passed",
  "warning",
  "failed",
  "unavailable",
  "waived",
] as const;
export type CheckStatus = (typeof CHECK_STATUSES)[number];

export const BUSINESS_ROLES = [
  "manufacturer",
  "importer",
  "trader",
  "logistics_provider",
  "distributor",
  "laboratory",
  "insurance_provider",
] as const;
export type BusinessRole = (typeof BUSINESS_ROLES)[number];

export const DOCUMENT_KINDS = [
  "registration_certificate",
  "director_id",
  "bank_letter",
  "license",
  "permit",
  "certificate",
  "power_of_attorney",
  "other",
] as const;
export type DocumentKind = (typeof DOCUMENT_KINDS)[number];

export const INCOTERMS = [
  "EXW",
  "FCA",
  "CPT",
  "CIP",
  "DAP",
  "DPU",
  "DDP",
  "unknown",
] as const;
export type Incoterm = (typeof INCOTERMS)[number];

export const OFFER_STATUSES = [
  "draft",
  "pending_moderation",
  "approved",
  "rejected",
  "archived",
] as const;
export type OfferStatus = (typeof OFFER_STATUSES)[number];

export const AVAILABILITY = ["in_stock", "on_order"] as const;
export type Availability = (typeof AVAILABILITY)[number];

export const QTY_UNITS = ["kg", "t", "pcs"] as const;
export type QtyUnit = (typeof QTY_UNITS)[number];

export const CURRENCIES = ["UZS", "USD", "EUR", "RUB", "CNY"] as const;
export type Currency = (typeof CURRENCIES)[number];

export const JURISDICTIONS = ["UZ", "RU", "KZ", "CN", "TR", "other"] as const;
export type Jurisdiction = (typeof JURISDICTIONS)[number];
