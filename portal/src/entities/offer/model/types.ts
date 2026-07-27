import type { Availability, OfferStatus, SaleMode } from "@/shared/config";

/** A file attached to an offer — photo (`image`) or document. */
export interface OfferFile {
  id: number;
  kind: "image" | "tds" | "certificate" | "other";
  file_name: string;
}

export interface OfferPayload {
  product_id?: number | null;
  product_text?: string | null;
  grade_text?: string | null;
  polymer_type?: string | null;
  availability: Availability;
  qty_available?: string | number | null;
  qty_unit: string;
  price?: string | number | null;
  currency: string;
  /** One of the Incoterm enum values; typed as string to tolerate unknowns. */
  incoterms: string;
  warehouse_city?: string | null;
  country?: string | null;
  min_order_qty?: string | number | null;
  description?: string | null;
  /** Production/sourcing lead time. Required by the API for made-to-order offers. */
  lead_time_days?: number | null;
  sale_mode?: SaleMode | null;
  /** Deal-readiness flags → badges on the market card. */
  accepts_rfq: boolean;
  accepts_contract: boolean;
  accepts_escrow: boolean;
}

export interface CompanyOffer extends OfferPayload {
  id: number;
  status: OfferStatus;
  moderation_note: string | null;
  created_at: string;
  /** Attached files in upload order. */
  files: OfferFile[];
  /** The first photo; null when the offer has none. */
  cover_file_id: number | null;
}
