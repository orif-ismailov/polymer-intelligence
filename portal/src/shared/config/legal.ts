/**
 * Facts the legal pages (`/privacy`, `/account-deletion`) state about the operator.
 *
 * One file on purpose: both app stores link to these pages, and every value here is
 * something the operator — not a developer — has to confirm. The bracketed values
 * are PLACEHOLDERS that nothing in the product knows yet; replace them before the
 * store submission. They are interpolated into all six locales, so a value changed
 * here changes every language at once.
 */

/** Legal name of the entity operating ai-imex.com and the mobile apps. */
export const LEGAL_OPERATOR_NAME = "[LEGAL ENTITY NAME — TO BE FILLED IN]";

/** Where privacy questions and deletion requests go. */
export const LEGAL_CONTACT_EMAIL = "[CONTACT EMAIL — TO BE FILLED IN]";

/** Hosting provider and the country the servers are in. */
export const LEGAL_HOSTING = "[HOSTING PROVIDER, COUNTRY — TO BE FILLED IN]";

/** Date of the current revision, as printed on both pages. */
export const LEGAL_UPDATED_AT = "25.09.2026";

/** The public site the policy covers. */
export const LEGAL_SITE = "ai-imex.com";

/** Values interpolated into every `legal.*` string. */
export const LEGAL_VALUES = {
  operator: LEGAL_OPERATOR_NAME,
  email: LEGAL_CONTACT_EMAIL,
  hosting: LEGAL_HOSTING,
  date: LEGAL_UPDATED_AT,
  site: LEGAL_SITE,
} as const;
