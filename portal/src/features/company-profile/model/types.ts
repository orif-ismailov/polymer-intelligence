import type { Availability, OfferFileLike } from "@/shared/config";

/**
 * A listing as the profile's «Продукты" tab paints it.
 *
 * `cas_number` is optional because the public catalog card does not carry it —
 * it arrives only on an offer's own detail payload. The row simply omits the CAS
 * line there rather than the tier forking.
 */
export interface CompanyProfileOffer {
  id: number;
  product_text: string | null;
  grade_text: string | null;
  polymer_type: string | null;
  availability: Availability;
  files: OfferFileLike[];
  cas_number?: string | null;
}

/**
 * The company profile's view model — what `/manufacturers/:id`,
 * `/cabinet/sellers/:id` and the public `/{directory}/:id` agree on.
 *
 * Both wire types satisfy this structurally, with no adapter:
 * `PublicCompanyProfile` (`/portal/market/companies/{id}`, authenticated) and
 * `PublicCompanyDetail` (`/public/directories/{slug}/{id}`, anonymous).
 *
 * The block at the bottom is optional for a reason worth knowing: the PUBLIC
 * payload is the richer one. `production_type`, `main_products`, `employees`,
 * `founded_year`, `export_countries` and `iso_certification` are registration
 * facts the storefront already showed and the cabinet's catalog endpoint never
 * returned. They are rendered when present, so the storefront keeps them and the
 * cabinet is simply quieter — rather than the storefront losing them to share
 * this sheet.
 *
 * Session state is absent on purpose: "do I own this company" is an
 * authenticated question, so it enters as the `isOwner` prop instead.
 */
export interface CompanyProfileCompany {
  id: number;
  legal_name: string | null;
  short_name: string | null;
  legal_form: string | null;
  legal_address: string | null;
  jurisdiction: string;
  registration_date: string | null;
  verified_at: string | null;
  logo_url: string | null;
  /** Public payload only — the cabinet's catalog endpoint does not carry it. */
  cover_url?: string | null;
  roles: string[];
  offer_count: number;
  offers: CompanyProfileOffer[];

  production_type?: string | null;
  main_products?: string | null;
  employees?: number | null;
  founded_year?: number | null;
  export_countries?: string[];
  iso_certification?: string | null;

  /**
   * Carrier questionnaire — public payload only, and only for a company that
   * filled one in. Optional for the same reason as the block above: the authed
   * `/portal/market/companies/{id}` payload behind `CabinetCompanyProfile` does
   * not carry it, and this interface is satisfied structurally by both.
   */
  logistics?: LogisticsProfileSnippet | null;

  /**
   * Published-review aggregate and first page. Optional for the same reason as
   * everything above it: the cabinet's catalog payload does not carry them, and
   * a required field would break `CabinetCompanyProfile`'s typecheck.
   */
  rating?: number | null;
  review_count?: number;
  reviews?: CompanyProfileReview[];
}

export interface CompanyProfileReview {
  id: number;
  rating: number;
  body: string | null;
  author_company_name: string | null;
  created_at: string;
}

/** Keys, not labels — see `PublicLogisticsSnippet` in `entities/public`. */
export interface LogisticsProfileSnippet {
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
  capability_images?: Record<string, string>;
}
