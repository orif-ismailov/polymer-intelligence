/**
 * A buyer's transport request to one carrier.
 *
 * Only the AUTHED resource lives in this slice. Reading a carrier's profile is
 * public and already served by `entities/public` (and SSR-prefetched) — a second
 * copy of that read here would be two caches for one page.
 */
export interface LogisticsRequest {
  id: number;
  public_id: string;
  number: string;
  buyer_company_id: number;
  cargo_name: string;
  /** Decimal STRING on the wire (precision); display through `formatQty`. */
  volume: string;
  volume_unit: string;
  packaging_type: string | null;
  special_requirements: string | null;
  from_country: string;
  from_city: string | null;
  to_country: string;
  to_city: string | null;
  contact_phone: string | null;
  status: LogisticsRequestStatus;
  created_at: string;
  buyer_name: string | null;
  /** Carriers who opened a conversation — the only signal a broadcast landed. */
  thread_count: number;
}

/**
 * One open request as a CARRIER sees it in the pool.
 *
 * A separate type rather than `LogisticsRequest` minus a field, mirroring the
 * backend: the pool payload deliberately carries no `contact_phone`, and
 * inheriting would mean a field added upstream silently becomes visible here.
 */
export interface LogisticsPoolItem {
  id: number;
  number: string;
  buyer_company_id: number;
  buyer_name: string | null;
  cargo_name: string;
  volume: string;
  volume_unit: string;
  packaging_type: string | null;
  special_requirements: string | null;
  from_country: string;
  from_city: string | null;
  to_country: string;
  to_city: string | null;
  status: LogisticsRequestStatus;
  created_at: string;
  /** This carrier's own thread, when it has already replied. */
  my_thread_id: number | null;
}

export interface LogisticsThread {
  id: number;
  logistics_request_id: number;
  request_number: string;
  carrier_company_id: number;
  /** The OTHER party, resolved for whoever is reading. */
  counterparty_name: string | null;
  my_role: "buyer" | "carrier" | "";
  cargo_name: string;
  created_at: string;
  updated_at: string;
}

export interface LogisticsMessage {
  id: number;
  author_company_id: number;
  body: string;
  has_file: boolean;
  file_name: string | null;
  created_at: string;
}

/**
 * The three dots on the request sheet are this, not form steps: the form is one
 * screen. `viewed` collapses into «отправлена» for the buyer — a carrier opening
 * the row is not news worth a state change on screen.
 */
export type LogisticsRequestStatus =
  | "submitted"
  | "viewed"
  | "in_progress"
  | "quoted"
  | "closed"
  | "rejected";

export interface LogisticsRequestCreatePayload {
  /** The BUYER's acting company — an account may belong to several. */
  company_id: number;
  cargo_name: string;
  volume: string;
  volume_unit: string;
  packaging_type?: string | null;
  special_requirements?: string | null;
  from_country: string;
  from_city?: string | null;
  to_country: string;
  to_city?: string | null;
}

/**
 * «Тип упаковки». Keys, resolved through `logisticsRequest.packaging.*`.
 *
 * Free text on the server (see the model's note): nothing filters on it, so a
 * new member here is a locale edit rather than a migration.
 */
export const LOGISTICS_PACKAGING_TYPES = [
  "containers",
  "big_bags",
  "bags",
  "bulk",
  "pallets",
  "iso_tank",
  "drums",
  "other",
] as const;

export type LogisticsPackagingType = (typeof LOGISTICS_PACKAGING_TYPES)[number];
