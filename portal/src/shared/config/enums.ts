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
  "production_license",
  "export_license",
  "certificate_of_origin",
  "iso_certificate",
  "compliance_certificate",
  "carrier_license",
  "liability_insurance",
  "service_contract",
  "accreditation_certificate",
] as const;
export type DocumentKind = (typeof DOCUMENT_KINDS)[number];

/**
 * Must match the backend `PriceBasis` enum verbatim (`app/models/enums.py`).
 *
 * It previously offered CIP and DPU — which the API rejects with a 422 — and
 * omitted FOB and CIF, which it accepts. Any value here that Pydantic does not
 * know is a form the user can fill in and never submit.
 */
export const INCOTERMS = [
  "EXW",
  "FCA",
  "FOB",
  "CIF",
  "CPT",
  "DAP",
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

/**
 * The `OfferFileKind` that is a product photo. Everything else attached to an
 * offer is a document (TDS, SDS, COA, certificate, lab passport).
 *
 * Named here rather than typed at each call site because it was got wrong: the
 * whole storefront filtered for `"photo"`, which the backend never emits, so no
 * public page displayed an offer photo and `og:image` was permanently absent.
 * A string literal repeated in five files is a bug waiting for the sixth.
 */
export const OFFER_PHOTO_KIND = "image";

/**
 * The offer-file shape every tier can supply.
 *
 * `file_name` is optional because the public payload omits it (`PublicOfferFile`
 * is `{id, kind}` — an uploader's filename is not a public register fact), while
 * the cabinet's `OfferFileRef` always carries one. Lives in `shared` so both
 * `features/product-detail` and `features/company-profile` can name it without
 * importing each other.
 */
export interface OfferFileLike {
  id: number;
  kind: string;
  file_name?: string;
}

/** Photos of an offer, in upload order (cover first). */
export function offerPhotoFiles<T extends { kind: string }>(files: readonly T[]): T[] {
  return files.filter((f) => f.kind === OFFER_PHOTO_KIND);
}

/** Everything on an offer that is NOT a photo — the documents strip and tab. */
export function offerDocumentFiles<T extends { kind: string }>(files: readonly T[]): T[] {
  return files.filter((f) => f.kind !== OFFER_PHOTO_KIND);
}

/**
 * How a seller trades an offer (backend `OfferSaleMode`). Orthogonal to
 * `AVAILABILITY`, which says whether the goods exist right now.
 */
export const SALE_MODES = ["from_stock", "made_to_order", "recurring_contract"] as const;
export type SaleMode = (typeof SALE_MODES)[number];

/**
 * Quantity units, in the spelling the rest of the stack uses.
 *
 * `MT` first and upper-case throughout: the backend column defaults to `"MT"`,
 * the Mini App writes `MT`/`KG`, and every mockup prints `500 MT` — the portal's
 * old lower-case `kg`/`t`/`pcs` was the only place a unit looked different, so
 * one offer's card read `500 t` next to another's `500 MT`.
 */
export const QTY_UNITS = ["MT", "KG", "PCS"] as const;
export type QtyUnit = (typeof QTY_UNITS)[number];

export const CURRENCIES = ["UZS", "USD", "EUR", "RUB", "CNY"] as const;
export type Currency = (typeof CURRENCIES)[number];

/**
 * `companies.jurisdiction` is a `varchar(2)` ISO country code, so every entry here
 * must be exactly two letters.
 *
 * An `"other"` option used to ship in this list. The service upper-cases the value,
 * so it reached Postgres as `"OTHER"` and blew the column width — a first-class,
 * selectable UI choice answered 500 (`StringDataRightTruncation`). Adding a country
 * means adding its real code, never a placeholder.
 */
export const JURISDICTIONS = ["UZ", "RU", "KZ", "CN", "TR"] as const;
export type Jurisdiction = (typeof JURISDICTIONS)[number];
