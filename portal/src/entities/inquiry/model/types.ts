/** A minimal offer summary embedded in an inquiry (OfferBrief). */
export interface InquiryOfferBrief {
  id: number;
  product_id: number | null;
  product_text: string | null;
  grade_text: string | null;
  price: string | number | null;
  currency: string;
  qty_unit: string;
}

export type InquiryStatus = "pending" | "approved" | "rejected";

/** Buyer-facing inquiry (OfferRequestOut) — moderation internals are hidden. */
export interface Inquiry {
  id: number;
  offer_id: number;
  status: InquiryStatus;
  quantity: string | number | null;
  qty_unit: string;
  target_price: string | number | null;
  currency: string | null;
  message: string | null;
  created_at: string;
  edited_at: string | null;
  offer: InquiryOfferBrief;
}

/** Body for creating an inquiry (mirror OfferRequestCreate + company_id). */
export interface InquiryPayload {
  company_id: number;
  quantity?: string | number | null;
  qty_unit?: string;
  target_price?: string | number | null;
  currency?: string | null;
  message?: string | null;
}
