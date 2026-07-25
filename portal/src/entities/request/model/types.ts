export type RequestStatus =
  | "new"
  | "viewed"
  | "in_progress"
  | "offer_sent"
  | "matched"
  | "closed"
  | "cancelled";

export interface RequestSummary {
  id: number;
  number: string;
  status: RequestStatus;
  created_at: string;
}

export interface RequestFile {
  id: number;
  file_name: string;
  mime_type: string | null;
  size_bytes: number | null;
}

export interface StatusHistoryEntry {
  from_status: RequestStatus | null;
  to_status: RequestStatus;
  created_at: string;
}

export interface RequestDetail extends RequestSummary {
  product_id: number | null;
  product_text: string | null;
  grade_text: string | null;
  polymer_type: string | null;
  volume: string | number;
  volume_unit: string;
  target_price: string | number | null;
  currency: string;
  incoterms: string;
  destination_country: string;
  port_or_city: string | null;
  desired_date: string | null;
  validity_days: number;
  urgency: string;
  comment: string | null;
  company_name: string | null;
  contact_name: string | null;
  phone: string | null;
  legal_address: string | null;
  files: RequestFile[];
  history: StatusHistoryEntry[];
}

/** Body for POST /portal/requests (RequestCreate + company_id). */
export interface RequestPayload {
  company_id: number;
  product_id?: number | null;
  product_text?: string | null;
  grade_text?: string | null;
  polymer_type?: string | null;
  volume: string | number;
  volume_unit?: string;
  target_price?: string | number | null;
  currency?: string;
  incoterms?: string;
  destination_country?: string;
  port_or_city?: string | null;
  desired_date?: string | null;
  validity_days?: number;
  urgency?: string;
  comment?: string | null;
  company_name?: string | null;
  contact_name?: string | null;
  phone?: string | null;
  legal_address?: string | null;
}
