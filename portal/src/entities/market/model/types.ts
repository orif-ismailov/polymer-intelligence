import type { Availability, SaleMode } from "@/shared/config";

import type { Inquiry } from "@/entities/inquiry";

/** A file reference on a catalog offer (image / TDS / certificate). */
export interface OfferFileRef {
  id: number;
  kind: string;
  file_name: string;
}

/** Public seller block on a seller-origin offer. */
export interface CatalogSeller {
  company_name: string | null;
  country: string | null;
  is_verified: boolean;
}

/**
 * A public (approved) catalog offer — mirror of the backend CatalogOfferOut.
 * `origin`/`display_name`/`company_verified` unify seller- and company-origin.
 */
export interface MarketOffer {
  id: number;
  product_id: number | null;
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
  published_at: string | null;
  files: OfferFileRef[];
  origin: string;
  display_name: string | null;
  company_verified: boolean;
  seller: CatalogSeller | null;
  is_own: boolean;
  /** P4: how the seller trades this offer, and what they are ready to do. */
  lead_time_days: number | null;
  sale_mode: SaleMode | null;
  accepts_rfq: boolean;
  accepts_contract: boolean;
  accepts_escrow: boolean;
  /** Per-ACCOUNT (not per-company): resolved server-side so the heart is correct
   *  on first paint rather than after a second round trip. */
  is_favorite: boolean;
  /** CONFIRMED business roles of the company behind the offer. Empty for
   *  seller-origin (Telegram) offers — no portal company, nothing confirmed. */
  business_roles: string[];
  /** P6: a passport is attached (anyone can upload one) versus we arranged the
   *  analysis. Two different claims, filtered separately in the market. */
  has_lab_passport: boolean;
  lab_verified: boolean;
  /** Sample terms, so the card can say "samples: 15 USD, ships in 3 days". */
  samples_available: boolean;
  sample_price: string | number | null;
  sample_dispatch_days: number | null;
}

/** Offer detail + the caller company's own inquiries on it (PortalMarketOfferDetail). */
export interface MarketOfferDetail extends MarketOffer {
  my_inquiries: Inquiry[];
}

export interface MarketFilters {
  q?: string;
  product_id?: number;
  availability?: Availability;
  country?: string;
  /** FR-L5 — two separate questions: "has an analysis" and "we arranged it".
   *  Undefined (or false) means "don't filter", never "show me the ones
   *  without". */
  has_lab_passport?: boolean;
  lab_verified?: boolean;
}
