import type { Availability, OfferFileLike } from "@/shared/config";

/**
 * A file on the sheet (photo / TDS / certificate / lab passport).
 *
 * An alias, not a second declaration: `features/company-profile` needs the same
 * shape and cannot import it from here (features do not import features), so the
 * one definition lives in `shared/config`.
 */
export type ProductDetailFile = OfferFileLike;

/**
 * The product sheet's view model — the fields `/market/:offerId` paints,
 * whichever payload it has.
 *
 * That page reads two: `PublicOfferDetail` (`/public/offers/{id}`, anonymous,
 * always) and — for a signed-in visitor, after hydration — `MarketOfferDetail`
 * (`/portal/market/{id}`, authenticated). Both satisfy this
 * shape **structurally** — there is no adapter and no mapping function, which is
 * the point: a field added to one wire type does not silently reach the sheet
 * unless it is declared here too.
 *
 * What is deliberately absent is the session/negotiation set — `is_own`,
 * `is_favorite`, `accepts_rfq`, `accepts_contract`, `accepts_escrow`,
 * `my_inquiries`, sample pricing. The public API withholds those on purpose
 * (`backend/app/schemas/public.py` treats its field list as a security
 * boundary), so anything derived from them enters the components as a **prop**
 * supplied by the cabinet page, never as a field read off the offer. That is
 * what lets these components server-render on the storefront, where there is no
 * session to read.
 */
export interface ProductDetailOffer {
  id: number;
  product_text: string | null;
  grade_text: string | null;
  polymer_type: string | null;
  availability: Availability;
  qty_available: string | number | null;
  qty_unit: string;
  price: string | number | null;
  currency: string;
  incoterms: string;
  warehouse_city: string | null;
  country: string | null;
  min_order_qty: string | number | null;
  description: string | null;
  display_name: string | null;
  company_verified: boolean;
  lead_time_days: number | null;
  has_lab_passport: boolean;
  lab_verified: boolean;
  samples_available: boolean;
  seller_company_id: number | null;
  manufacturer?: string | null;
  key_properties?: string[];
  applications?: string[];
  cas_number?: string | null;
  hs_code?: string | null;
  files: ProductDetailFile[];
}

