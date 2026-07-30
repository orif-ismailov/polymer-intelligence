import type { BusinessRole, DocumentKind } from "@/shared/config";

export const DEFAULT_JURISDICTION = "UZ";

// ── Step map ─────────────────────────────────────────────────────────────────
//
// The registration mockups (docs/new-design/register.jpeg) run
// «Тип компании → Данные → Проверка → Подпись». Signing is merged into step 1
// because an E-IMZO certificate carries the company's STIR: signing first fills
// the requisites in, so it has to be offered *before* the form, not after it.
// Bank + documents sit between the form and the checks — the case's
// `bank_requisites` / `documents_complete` checks read what they collect.

export const WIZARD_STEP_TYPE = 1;
export const WIZARD_STEP_DETAILS = 2;
export const WIZARD_STEP_BANK = 3;
export const WIZARD_STEP_DOCUMENTS = 4;
export const WIZARD_STEP_REVIEW = 5;

export const WIZARD_FIRST_STEP = WIZARD_STEP_TYPE;
export const WIZARD_STEP_COUNT = WIZARD_STEP_REVIEW;

/**
 * The four account types on «Выберите тип аккаунта», each mapped to the backend
 * `company_business_role` it declares.
 *
 * Two are exact (`manufacturer`, `trader`); the mockup's «Покупатель» and
 * «Поставщик» have no same-named member in the enum, so they map to the nearest
 * one that exists — buying-side is `importer`, selling-side is `distributor`.
 * Sending anything else 422s, and the enum is a Postgres type, so widening it
 * would be a migration rather than a copy change.
 */
export interface AccountTypeSpec {
  id: string;
  role: BusinessRole;
}

export const ACCOUNT_TYPES: readonly AccountTypeSpec[] = [
  { id: "buyer", role: "importer" },
  { id: "supplier", role: "distributor" },
  { id: "manufacturer", role: "manufacturer" },
  { id: "trader", role: "trader" },
];

/**
 * «Форма собственности». The column is free text (`companies.legal_form`), and
 * rows predating this select hold exactly these short forms — so the option
 * *value* is the short form and only the label is the full name. An unrecognised
 * existing value is offered back as its own option rather than being rewritten.
 */
export const LEGAL_FORMS = ["ООО", "ЧП", "АО", "СП", "ИП", "ГУП"] as const;

/** E-IMZO signing methods on the «Электронная подпись» panel. */
export const EIMZO_METHODS = ["usb_token", "mobile_id", "cloud_id"] as const;
export type EimzoMethod = (typeof EIMZO_METHODS)[number];

/** Only the desktop CAPIWS module is wired; the other two are operator-pending. */
export const EIMZO_AVAILABLE_METHOD: EimzoMethod = "usb_token";

/** Document kinds surfaced as dropzones in the wizard. */
export const WIZARD_DOCUMENT_KINDS: readonly DocumentKind[] = [
  "registration_certificate",
  "bank_letter",
  "director_id",
  "license",
];

/** Always-required documents regardless of other inputs. */
export const ALWAYS_REQUIRED_DOCS: readonly DocumentKind[] = ["registration_certificate"];

/** Deep-link map: which wizard step a failing verification check points back to. */
export const CHECK_TO_STEP: Record<string, number> = {
  tax_id_format: WIZARD_STEP_DETAILS,
  eimzo_signature: WIZARD_STEP_TYPE,
  bank_requisites: WIZARD_STEP_BANK,
  documents_complete: WIZARD_STEP_DOCUMENTS,
  manual_kyb: WIZARD_STEP_REVIEW,
};

/**
 * Which glyph and label each verification check wears on «Проверка компании».
 * Ordered as the mockup lists them; a check the API returns that is not here
 * still renders, with the fallback glyph.
 */
export const CHECK_ORDER: readonly string[] = [
  "tax_id_format",
  "eimzo_signature",
  "documents_complete",
  "bank_requisites",
  "manual_kyb",
];
