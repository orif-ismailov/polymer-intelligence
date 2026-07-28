/** Sample requests (P6): a buyer asks a seller for material to hold. */

export type SampleRequestStatus =
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
