/**
 * The company profile's tab rail, in mockup order
 * (`docs/new-design/company_profile.jpeg`).
 *
 * Shared so the cabinet sheets and the public directory profile show the same
 * four entries with the same labels (`companyProfile.tabs.*`). `reviews` and
 * `documents` are chrome for surfaces that do not exist yet.
 */
export const COMPANY_PROFILE_TAB_IDS = ["about", "products", "reviews", "documents"] as const;

export type CompanyProfileTabId = (typeof COMPANY_PROFILE_TAB_IDS)[number];
