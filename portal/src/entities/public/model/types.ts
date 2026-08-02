/**
 * Wire types for `/api/v1/public` — the anonymous storefront surface.
 *
 * Mirrors `backend/app/schemas/public.py`. Kept separate from the cabinet's
 * market types on purpose: those carry `is_favorite`, inquiry blocks and other
 * per-account state that the public API does not return, and sharing one type
 * would mean every public component had to null-check fields that can never
 * arrive.
 */

export interface PublicOfferFile {
  id: number;
  kind: string;
}

export interface PublicOfferCard {
  id: number;
  product_id: number | null;
  product_text: string | null;
  grade_text: string | null;
  polymer_type: string | null;
  availability: "in_stock" | "on_order";
  qty_available: string | null;
  qty_unit: string;
  price: string | null;
  currency: string;
  incoterms: string;
  warehouse_city: string | null;
  country: string | null;
  published_at: string | null;
  files: PublicOfferFile[];
  origin: string;
  display_name: string | null;
  company_verified: boolean;
  lead_time_days: number | null;
  min_order_qty: string | null;
  business_roles: string[];
  has_lab_passport: boolean;
  lab_verified: boolean;
  samples_available: boolean;
}

export interface PublicOfferDetail extends PublicOfferCard {
  description: string | null;
  manufacturer: string | null;
  key_properties: string[];
  applications: string[];
  cas_number: string | null;
  hs_code: string | null;
  seller_company_id: number | null;
  seller_display_name: string | null;
}

export interface PublicOfferList {
  items: PublicOfferCard[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * A carrier's questionnaire as the storefront receives it.
 *
 * Every list holds KEYS, not display strings — the same ones the registration
 * wizard writes (`LOGISTICS_SERVICE_OPTIONS` and friends in
 * `features/company-wizard/model/constants`), resolved for display through the
 * `wizard.logistics.*` i18n tree. Rendering a raw value would print
 * `international_road` on the page.
 */
export interface PublicLogisticsSnippet {
  city: string | null;
  description: string | null;
  services: string[];
  from_countries: string[];
  to_countries: string[];
  popular_routes: string[];
  cargo_types: string[];
  capabilities: string[];
  tariff_model: string | null;
  years_experience: number | null;
  projects_completed: number | null;
  /** `{capability_key: url}` — only the keys that actually have a picture. */
  capability_images: Record<string, string>;
}

/**
 * One published review. The author COMPANY is named; the person is not — a
 * review is a company's position, and the backend deliberately never serialises
 * `author_account_id`.
 */
export interface PublicReview {
  id: number;
  rating: number;
  body: string | null;
  author_company_name: string | null;
  created_at: string;
}

export interface PublicCompanyCard {
  id: number;
  public_id: string;
  legal_name: string | null;
  short_name: string | null;
  legal_address: string | null;
  jurisdiction: string;
  logo_url: string | null;
  /** Hero image behind the logo; NULL when none was uploaded. */
  cover_url: string | null;
  verified_at: string | null;
  roles: string[];
  offer_count: number;
  production_type: string | null;
  main_products: string | null;
  employees: number | null;
  founded_year: number | null;
  export_countries: string[];
  iso_certification: string | null;
  /** NULL for a company that never filled in a carrier questionnaire. */
  logistics: PublicLogisticsSnippet | null;
  /** NULL, not 0, when nobody has reviewed yet — «нет отзывов» ≠ «оценка 0». */
  rating: number | null;
  review_count: number;
}

export interface PublicCompanyList {
  items: PublicCompanyCard[];
  total: number;
  limit: number;
  offset: number;
  role: string;
}

export interface PublicCompanyDetail extends PublicCompanyCard {
  registration_date: string | null;
  legal_form: string | null;
  offers: PublicOfferCard[];
  /** First page, inline — see the backend note on why not a second endpoint. */
  reviews: PublicReview[];
}

export interface PublicCategory {
  product_id: number;
  code: string;
  label: string;
  offer_count: number;
}

/** One option in a storefront filter dropdown, aggregated from the live catalog. */
export interface PublicFacet {
  value: string;
  label: string;
  offer_count: number;
}

export interface PublicStats {
  offer_count: number;
  company_count: number;
  country_count: number;
  directory_counts: Record<string, number>;
  /**
   * Filter options for the home sidebar's four dropdowns. They ride on `/stats`
   * (rather than their own endpoint) because that call is already prefetched
   * server-side for this page.
   */
  countries: PublicFacet[];
  incoterms: PublicFacet[];
  companies: PublicFacet[];
}

export interface PublicQuote {
  product_id: number;
  code: string;
  label: string;
  price: string;
  currency: string;
  unit: string;
  observed_on: string;
  change_pct: string | null;
}

export interface PublicNewsCard {
  id: number;
  headline: string;
  summary: string | null;
  published_at: string | null;
  importance: string | null;
  category: string | null;
}

export interface PublicOfferFilters {
  q?: string;
  product_id?: number;
  availability?: "in_stock" | "on_order";
  country?: string;
  has_lab_passport?: boolean;
  lab_verified?: boolean;
  seller_company_id?: number;
}
