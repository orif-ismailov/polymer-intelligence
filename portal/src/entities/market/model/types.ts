import type { Availability } from "@/shared/config";

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
}
