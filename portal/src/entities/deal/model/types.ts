/**
 * Deal domain types (R4 / P2).
 *
 * Money and quantities are strings end to end — they are contract terms, and a
 * float round-trip is a wrong price. Format for display, never parse to Number
 * for arithmetic.
 */

export type DealStatus =
  | "negotiation"
  | "contract_pending"
  | "contract_signed"
  | "payment_pending"
  | "paid_escrow"
  | "shipped"
  | "delivered"
  | "completed"
  | "cancelled"
  | "disputed";

export type DealRole = "buyer" | "seller";

export type DealDocumentKind = "contract" | "invoice" | "lab_passport" | "transport" | "other";

export interface DealParty {
  company_id: number;
  name: string | null;
  logo_url: string | null;
  verified: boolean;
  roles: string[];
}

export interface DealTimelineEntry {
  id: number;
  from_status: DealStatus | null;
  to_status: DealStatus;
  actor_kind: "buyer" | "seller" | "staff" | "system";
  reason: string | null;
  created_at: string;
}

export interface DealDocument {
  id: number;
  kind: DealDocumentKind;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by_company_id: number;
  uploaded_by_company_name: string | null;
  revoked: boolean;
  revoked_reason: string | null;
  created_at: string;
}

export interface DealMessage {
  id: number;
  body: string;
  file_name: string | null;
  has_file: boolean;
  author_account_id: number;
  author_company_id: number;
  author_company_name: string | null;
  /** True when this side wrote it — drives left/right alignment. */
  mine: boolean;
  created_at: string;
}

export interface DealMessagePage {
  items: DealMessage[];
  last_id: number | null;
}

export interface DealSummary {
  id: number;
  public_id: string;
  number: string;
  status: DealStatus;
  role: DealRole;
  counterparty: DealParty;
  amount: string | null;
  currency: string;
  contract_id: number | null;
  needs_action: boolean;
  created_at: string;
  updated_at: string;
}

export interface DealCounters {
  total: number;
  needs_action: number;
  active: number;
  closed: number;
}

export interface DealList {
  items: DealSummary[];
  counters: DealCounters;
}

export type EscrowStatus = "pending" | "funded" | "released" | "refunded";

/**
 * The money side of a deal (R4 / P3). Status and dates only: the buyer pays an
 * invoice issued by the partner bank, so there is nothing to act on here and no
 * account details to show — the platform holds none.
 */
export interface DealEscrow {
  status: EscrowStatus;
  amount: string;
  currency: string;
  funded_at: string | null;
  released_at: string | null;
  refunded_at: string | null;
}

export interface DealDetail extends DealSummary {
  buyer: DealParty;
  seller: DealParty;
  request_id: number | null;
  offer_id: number | null;
  contract_status: string | null;
  cancelled_reason: string | null;
  timeline: DealTimelineEntry[];
  documents: DealDocument[];
  /**
   * Statuses this side may move to right now, straight from the server's state
   * machine. The action bar renders from this — the machine is never
   * re-implemented here.
   */
  available_transitions: DealStatus[];
  /** Null until the contract is signed and the invoice is raised. */
  escrow: DealEscrow | null;
}

export interface RfqResponse {
  id: number;
  request_id: number;
  company_id: number;
  company_name: string | null;
  company_verified: boolean;
  price: string;
  currency: string;
  qty: string;
  qty_unit: string;
  incoterms: string | null;
  lead_time_days: number | null;
  comment: string | null;
  status: "submitted" | "accepted" | "not_selected" | "withdrawn";
  deal_id: number | null;
  created_at: string;
}

/**
 * A quote this company filed, with the tender it answers.
 *
 * The tender half is the same anonymized `MarketRequest` the open list shows —
 * no buyer identity, even though the quote is ours. `request_open` is false once
 * the tender stops accepting quotes, which is what makes a two-month-old
 * «Отправлено» readable.
 */
export interface MyRfqResponse {
  id: number;
  request_id: number;
  price: string;
  currency: string;
  qty: string;
  qty_unit: string;
  incoterms: string | null;
  lead_time_days: number | null;
  comment: string | null;
  status: RfqResponse["status"];
  created_at: string;
  request: MarketRequest;
  request_open: boolean;
}

export interface RfqResponsePayload {
  price: string;
  currency: string;
  qty: string;
  qty_unit: string;
  incoterms?: string | null;
  lead_time_days?: number | null;
  comment?: string | null;
}

export interface MarketRequest {
  id: number;
  product: string | null;
  grade: string | null;
  volume: string;
  volume_unit: string;
  incoterms: string;
  destination_country: string;
  port_or_city: string | null;
  desired_date: string | null;
  validity_days: number;
  urgency: string;
  required_docs: string[];
  created_at: string;
  my_response_id: number | null;
  my_response_status: RfqResponse["status"] | null;
}
