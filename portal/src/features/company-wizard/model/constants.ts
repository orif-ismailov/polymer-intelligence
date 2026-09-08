import type { BusinessRole, DocumentKind } from "@/shared/config";

export const DEFAULT_JURISDICTION = "UZ";

/** Account-type id that unlocks the manufacturer registration branch. */
export const MANUFACTURER_ACCOUNT_TYPE = "manufacturer";

/** Account-type id that unlocks the logistics registration branch. */
export const LOGISTICS_ACCOUNT_TYPE = "logistics";

/** Account-type id that unlocks the laboratory registration branch. */
export const LABORATORY_ACCOUNT_TYPE = "laboratory";

// ── Default (non-typed) step map ──────────────────────────────────────────────
//
// «Тип → Данные → Банк → Документы → Проверка». Signing is merged into step 1.

export const WIZARD_STEP_TYPE = 1;
export const WIZARD_STEP_DETAILS = 2;
export const WIZARD_STEP_BANK = 3;
export const WIZARD_STEP_DOCUMENTS = 4;
export const WIZARD_STEP_REVIEW = 5;

export const WIZARD_FIRST_STEP = WIZARD_STEP_TYPE;
export const WIZARD_DEFAULT_STEP_COUNT = WIZARD_STEP_REVIEW;

// ── Manufacturer step map (docs/new-design/companys_list.jpeg) ────────────────
//
// Type is still step 1 (shared). Then: legal+logo → production → catalog →
// certificates → buyer requirements → almost-ready / submit. Bank is omitted;
// factory certificates replace the generic documents step.

export const MFR_STEP_TYPE = 1;
export const MFR_STEP_DETAILS = 2;
export const MFR_STEP_PRODUCTION = 3;
export const MFR_STEP_CATALOG = 4;
export const MFR_STEP_CERTIFICATES = 5;
export const MFR_STEP_BUYER = 6;
export const MFR_STEP_REVIEW = 7;
export const MFR_STEP_COUNT = MFR_STEP_REVIEW;

// ── Logistics step map (docs/new-design/logist_reg_flow.jpeg) ─────────────────
//
// Type → company info (+logo) → services → geography → specialisation →
// tariffs+documents → review. Bank is omitted; carrier docs replace the generic
// documents step (bank_letter is one of those slots).

export const LOG_STEP_TYPE = 1;
export const LOG_STEP_DETAILS = 2;
export const LOG_STEP_SERVICES = 3;
export const LOG_STEP_GEOGRAPHY = 4;
export const LOG_STEP_SPECIALIZATION = 5;
export const LOG_STEP_TARIFFS_DOCS = 6;
export const LOG_STEP_REVIEW = 7;
export const LOG_STEP_COUNT = LOG_STEP_REVIEW;

// ── Laboratory step map (docs/new-design/labaratory_reg_flow.jpeg) ────────────
//
// Type → basic info (+logo, city, website, contacts, description) →
// licenses/accreditation → review (Модерация). Bank omitted. Equipment /
// research list / prices / contacts steps are named on the mockup but have no
// field designs yet — only the visible missing fields ship now.

export const LAB_STEP_TYPE = 1;
export const LAB_STEP_DETAILS = 2;
export const LAB_STEP_LICENSES = 3;
export const LAB_STEP_REVIEW = 4;
export const LAB_STEP_COUNT = LAB_STEP_REVIEW;

/**
 * The five account types on «Выберите тип аккаунта», each mapped to the backend
 * `company_business_role`(s) it declares.
 *
 * A company may belong to **exactly one** of these cards — never manufacturer and
 * trader, buyer and logistics, etc. The backend rejects cross-type mixes.
 *
 * «Дистрибьютор/Трейдер» is one card that declares both roles — the enum has no
 * combined member, and a single nearest pick would lie about half the label.
 * «Покупатель» maps to `importer` (no `buyer` member). Sending anything outside
 * the Postgres enum 422s.
 */
export interface AccountTypeSpec {
  id: string;
  roles: readonly BusinessRole[];
}

export const ACCOUNT_TYPES: readonly AccountTypeSpec[] = [
  { id: "buyer", roles: ["importer"] },
  { id: "distributor", roles: ["distributor", "trader"] },
  { id: "manufacturer", roles: ["manufacturer"] },
  { id: "logistics", roles: ["logistics_provider"] },
  { id: "laboratory", roles: ["laboratory"] },
];

export function isManufacturerType(accountType: string): boolean {
  return accountType === MANUFACTURER_ACCOUNT_TYPE;
}

export function isLogisticsType(accountType: string): boolean {
  return accountType === LOGISTICS_ACCOUNT_TYPE;
}

export function isLaboratoryType(accountType: string): boolean {
  return accountType === LABORATORY_ACCOUNT_TYPE;
}

export function wizardStepCount(accountType: string): number {
  if (isManufacturerType(accountType)) return MFR_STEP_COUNT;
  if (isLogisticsType(accountType)) return LOG_STEP_COUNT;
  if (isLaboratoryType(accountType)) return LAB_STEP_COUNT;
  return WIZARD_DEFAULT_STEP_COUNT;
}

/**
 * «Форма собственности». The column is free text (`companies.legal_form`), and
 * rows predating this select hold exactly these short forms — so the option
 * *value* is the short form and only the label is the full name. An unrecognised
 * existing value is offered back as its own option rather than being rewritten.
 */
export const LEGAL_FORMS = ["ООО", "ЧП", "АО", "СП", "ИП", "ГУП"] as const;

/** Document kinds surfaced as dropzones in the default wizard. */
export const WIZARD_DOCUMENT_KINDS: readonly DocumentKind[] = [
  "registration_certificate",
  "bank_letter",
  "director_id",
  "license",
];

/** Always-required documents regardless of other inputs (default flow). */
export const ALWAYS_REQUIRED_DOCS: readonly DocumentKind[] = ["registration_certificate"];

/**
 * Factory certificate slots on the manufacturer certificates step.
 * None are hard-required to advance — moderation reviews them — but
 * `registration_certificate` is still required when E-IMZO did not lock identity.
 */
export const MANUFACTURER_CERT_KINDS: readonly DocumentKind[] = [
  "production_license",
  "export_license",
  "certificate_of_origin",
  "iso_certificate",
  "compliance_certificate",
  "other",
];

/**
 * Carrier document slots on the logistics tariffs/documents step
 * (`logist_reg_flow.jpeg` «Необходимые документы»). Optional to advance;
 * registration certificate still required without E-IMZO.
 */
export const LOGISTICS_DOC_KINDS: readonly DocumentKind[] = [
  "carrier_license",
  "certificate",
  "liability_insurance",
  "iso_certificate",
  "service_contract",
  "bank_letter",
];

/**
 * Accreditation slots on the laboratory licenses step
 * (`labaratory_reg_flow.jpeg` «Аккредитации и документы»). Optional to advance;
 * registration certificate still required without E-IMZO.
 */
export const LABORATORY_DOC_KINDS: readonly DocumentKind[] = [
  "iso_certificate",
  "accreditation_certificate",
  "certificate",
];

/** Production-type select options (value = stored string). */
export const PRODUCTION_TYPES = [
  "polymers",
  "petrochemicals",
  "compounds",
  "recycling",
  "other",
] as const;

/** Main-products select options. */
export const MAIN_PRODUCT_OPTIONS = [
  "pp",
  "hdpe",
  "ldpe",
  "pvc",
  "pet",
  "abs",
  "other",
] as const;

/** ISO certification select options. */
export const ISO_OPTIONS = [
  "iso_9001",
  "iso_14001",
  "iso_45001",
  "iso_22000",
  "none",
] as const;

export const MARKET_OPTIONS = ["domestic", "export"] as const;
export type MarketOption = (typeof MARKET_OPTIONS)[number];

export const EXPORT_COUNTRY_OPTIONS = [
  "KZ",
  "RU",
  "TJ",
  "KG",
  "TM",
  "CN",
  "TR",
  "AE",
  "other",
] as const;

export const FINANCIAL_REQUIREMENT_KEYS = [
  "bank_guarantee",
  "letter_of_credit",
  "payment_deferral",
  "prepayment",
] as const;
export type FinancialRequirementKey = (typeof FINANCIAL_REQUIREMENT_KEYS)[number];

export const ADDITIONAL_REQUIREMENT_KEYS = [
  "financial_reporting",
  "market_experience",
  "licenses_certificates",
  "end_products_info",
  "production_photos",
  "other",
] as const;
export type AdditionalRequirementKey = (typeof ADDITIONAL_REQUIREMENT_KEYS)[number];

// ── Logistics options (logist_reg_flow.jpeg) ──────────────────────────────────

/** Step 2 services checklist. */
export const LOGISTICS_SERVICE_OPTIONS = [
  "international_road",
  "rail",
  "sea",
  "air",
  "multimodal",
  "customs_clearance",
  "export_clearance",
  "import_clearance",
  "certification",
  "cargo_insurance",
  "warehouse",
  "consolidation",
  "container_transport",
] as const;
export type LogisticsService = (typeof LOGISTICS_SERVICE_OPTIONS)[number];

/** «Откуда (страны-поставщики)». */
export const LOGISTICS_FROM_COUNTRIES = [
  "CN",
  "IR",
  "RU",
  "KZ",
  "TR",
  "AE",
  "other",
] as const;

/** «Куда (страны-получатели)». */
export const LOGISTICS_TO_COUNTRIES = ["UZ", "KZ", "KG", "TJ", "TM", "other"] as const;

/** Preset popular routes shown as selectable rows. */
export const LOGISTICS_POPULAR_ROUTES = [
  "shanghai_tashkent",
  "tehran_tashkent",
  "bandar_abbas_tashkent",
  "moscow_tashkent",
  "kazan_tashkent",
] as const;
export type LogisticsPopularRoute = (typeof LOGISTICS_POPULAR_ROUTES)[number];

/** Cargo specialisation grid. */
export const LOGISTICS_CARGO_TYPES = [
  "petrochemicals_polymers",
  "chemical_products",
  "liquid_bulk",
  "dangerous_goods_adr",
  "container_shipping",
  "big_bags",
  "other_cargo",
] as const;
export type LogisticsCargoType = (typeof LOGISTICS_CARGO_TYPES)[number];

/** «Возможности компании» checklist. */
export const LOGISTICS_CAPABILITIES = [
  "own_trucks",
  "own_rail_wagons",
  "sea_containers",
  "storage_facilities",
  "customs_warehouse",
  "foreign_offices",
  "customs_brokers",
] as const;
export type LogisticsCapability = (typeof LOGISTICS_CAPABILITIES)[number];

/** Tariff model — single choice on the tariffs step. */
export const LOGISTICS_TARIFF_MODELS = [
  "individual",
  "per_container",
  "per_ton",
  "per_km",
  "minimum_order",
] as const;
export type LogisticsTariffModel = (typeof LOGISTICS_TARIFF_MODELS)[number];

// ── Laboratory ────────────────────────────────────────────────────────────────
//
// Keys, resolved through `wizard.laboratory.*` / `labRequest.*`. Shared by the
// registration wizard (what a lab OFFERS) and the request form (what a buyer
// ASKS for) so the two vocabularies cannot drift apart — a lab that lists `dsc`
// and a request that asks for `dsc` have to mean the same thing.

/** «Необходимые исследования» / a laboratory's method list. */
export const LAB_METHODS = [
  "mfi",
  "density",
  "tensile_strength",
  "elongation",
  "impact_strength",
  "dsc",
  "ftir",
  "tga",
  "ash_content",
  "moisture",
  "vicat",
  "hardness",
  "melting_point",
  "carbon_black",
  "oit",
  "rheology",
] as const;
export type LabMethod = (typeof LAB_METHODS)[number];

/** «Тип исследований». */
export const LAB_STUDY_TYPES = [
  "full_passport",
  "single_method",
  "comparison",
  "incoming_control",
  "certification",
] as const;
export type LabStudyType = (typeof LAB_STUDY_TYPES)[number];

/** «Цель исследования». */
export const LAB_PURPOSES = [
  "quality_and_compatibility",
  "supplier_check",
  "certification",
  "dispute",
  "rnd",
] as const;
export type LabPurpose = (typeof LAB_PURPOSES)[number];

/** Accreditations a laboratory publishes on its profile. */
export const LAB_ACCREDITATIONS = [
  "iso_17025",
  "national_accreditation",
  "iso_9001",
  "gost_certified",
] as const;
export type LabAccreditation = (typeof LAB_ACCREDITATIONS)[number];

/** Deep-link map: which wizard step a failing verification check points back to. */
export const CHECK_TO_STEP: Record<string, number> = {
  tax_id_format: WIZARD_STEP_DETAILS,
  // `eimzo_signature` is deliberately absent: registration no longer signs
  // anything, so no step of this wizard can satisfy that check and a deep link
  // would land the applicant on a screen that cannot help. It is confirmed from
  // «Статус проверки» instead. The check keeps its place in CHECK_ORDER so cases
  // that WERE signed still render it.
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
  // `eimzo_signature` is NOT listed: `StepReview` renders this array as
  // placeholder rows before the case exists, so keeping it promised every
  // applicant a check registration can no longer produce — «Подпись E-IMZO ·
  // Ожидание» next to four checks that do run. A case that really carries the
  // check (one confirmed from «Статус проверки») still renders it: those rows
  // come from the API, and `checkRank` sorts an unlisted type last.
  "documents_complete",
  "bank_requisites",
  "manual_kyb",
];

/** Years offered on «Год основания завода» — newest first. */
export function foundationYearOptions(now = new Date().getFullYear()): number[] {
  const years: number[] = [];
  for (let y = now; y >= 1950; y -= 1) years.push(y);
  return years;
}
