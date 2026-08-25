/** Sample requests (P6): a buyer asks a seller for material to hold. */

export type SampleRequestStatus =
  /**
   * Asked, but NOT yet with the seller: this offer demands a signed
   * письмо-обязательство first (P7.a W8). The seller is not notified and cannot
   * act until the buyer signs, so the buyer's own row is the only place that can
   * say a signature is still owed.
   */
  | "pending_letter"
  | "requested"
  | "accepted"
  | "declined"
  | "sent"
  | "received"
  | "rejected_by_buyer";

export interface SampleRequest {
  id: number;
  offer_id: number;
  offer_title: string | null;
  status: SampleRequestStatus;
  buyer_company_id: number;
  seller_company_id: number;
  /** The OTHER side's name, resolved server-side (no lookup per row). */
  counterparty_name: string | null;
  /** Which side the caller is on, so one component renders both tabs. */
  my_role: "buyer" | "seller";
  /**
   * What the CALLER may do right now, straight from the server's table. The UI
   * never re-derives the machine — it would be a second copy to keep in sync,
   * and the two would disagree exactly when it mattered.
   */
  available_transitions: SampleRequestStatus[];
  qty: string | null;
  delivery_address: string;
  courier: string | null;
  tracking_ref: string | null;
  decline_reason: string | null;
  accepted_at: string | null;
  sent_at: string | null;
  received_at: string | null;
  created_at: string;
  /** Whether this request carries a commitment letter at all. */
  letter_required: boolean;
  letter_signed_at: string | null;
  letter_number: string | null;
}

/** The letter itself — fetched per sample, the PDF separately. */
export interface SampleLetter {
  number: string | null;
  sha256: string | null;
  signed_at: string | null;
  /** The seller's clause AS SIGNED — a snapshot, never the live offer text. */
  terms: string | null;
  required: boolean;
}

export interface SampleRequestPayload {
  company_id: number;
  qty?: string | null;
  delivery_address: string;
}

export interface SampleTransitionPayload {
  company_id: number;
  to_status: SampleRequestStatus;
  reason?: string | null;
  qty?: string | null;
  courier?: string | null;
  tracking_ref?: string | null;
}

export type SampleSide = "incoming" | "sent";
