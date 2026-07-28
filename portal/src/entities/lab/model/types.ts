/** Laboratory analysis orders (P6). The analysis itself is a manual process:
 *  we arrange it with a partner lab and upload the passport that comes back. */

export type LabOrderStatus =
  | "submitted"
  | "accepted"
  | "sample_awaited"
  | "in_analysis"
  | "done"
  | "rejected";

/** The order as its customer sees it. Statuses are moved by staff, not here. */
export interface LabOrder {
  id: number;
  number: string;
  status: LabOrderStatus;
  company_id: number;
  offer_id: number | null;
  deal_id: number | null;
  substance_id: number | null;
  sample_volume: string | null;
  comment: string | null;
  /** Who is doing the work, once we have agreed it with a laboratory. */
  lab_partner_name: string | null;
  operator_note: string | null;
  rejected_reason: string | null;
  /** Where the passport ended up, so the client can link straight to it. */
  result_offer_file_id: number | null;
  result_deal_document_id: number | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LabOrderPayload {
  offer_id?: number | null;
  deal_id?: number | null;
  substance_id?: number | null;
  sample_volume?: string | null;
  comment?: string | null;
}

/** Statuses that mean the order is still moving. */
export const LAB_ORDER_LIVE: readonly LabOrderStatus[] = [
  "submitted",
  "accepted",
  "sample_awaited",
  "in_analysis",
];
