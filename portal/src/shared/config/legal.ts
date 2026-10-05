/**
 * Facts the legal pages (`/privacy`, `/account-deletion`) state about the operator.
 *
 * One file on purpose: both app stores link to these pages, and every value here is
 * something the operator — not a developer — has to confirm. The bracketed values
 * are PLACEHOLDERS that nothing in the product knows yet; replace them before the
 * store submission. They are interpolated into all six locales, so a value changed
 * here changes every language at once.
 */

/**
 * Legal name of the entity operating ai-imex.com and the mobile apps. IMEX is its
 * own company — not Allinsan LLC, which only owns the Play developer account.
 */
export const LEGAL_OPERATOR_NAME = "«IMEX INDUSTRIAL GROUP CA» MCHJ";

/**
 * Registered address. Kept in the original wording in every locale — it is the
 * address on the registration, not a translation of it.
 */
export const LEGAL_OPERATOR_ADDRESS =
  "г. Ташкент, Алмазарский район, МФЙ Гани Азамов, улица Галаба, дом 9";

/** ИНН / STIR. */
export const LEGAL_OPERATOR_TIN = "312 616 547";

/** Display form, and the `tel:` form of the same number. */
export const LEGAL_OPERATOR_PHONE = "+998 77 391 88 88";
export const LEGAL_OPERATOR_PHONE_HREF = "tel:+998773918888";

/** Bank requisites printed in the footer. */
export const LEGAL_BANK_ACCOUNT = "20208000907356860001";
export const LEGAL_BANK_NAME = "АКБ «КАПИТАЛБАНК»";
export const LEGAL_BANK_MFO = "01088";

/** Where privacy questions and deletion requests go. */
export const LEGAL_CONTACT_EMAIL = "support@ai-imex.com";

/** Hosting provider and the country the servers are in. */
export const LEGAL_HOSTING = "Best Internet Solution, Uzbekistan";

/** Date of the current revision, as printed on both pages. */
export const LEGAL_UPDATED_AT = "05.10.2026";

/** The public site the policy covers. */
export const LEGAL_SITE = "ai-imex.com";

/** Values interpolated into every `legal.*` string. */
export const LEGAL_VALUES = {
  operator: LEGAL_OPERATOR_NAME,
  address: LEGAL_OPERATOR_ADDRESS,
  tin: LEGAL_OPERATOR_TIN,
  email: LEGAL_CONTACT_EMAIL,
  hosting: LEGAL_HOSTING,
  date: LEGAL_UPDATED_AT,
  site: LEGAL_SITE,
} as const;
