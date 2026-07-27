import type { Availability, OfferStatus } from "@/shared/config";

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
