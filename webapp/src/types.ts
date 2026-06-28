/**
 * TypeScript interfaces mirroring backend/app/schemas/webapp.py.
 *
 * Field names match the backend schemas exactly (snake_case) so JSON responses
 * deserialise without transformation.
 *
 * Source of truth: backend/app/schemas/webapp.py (03-01 contract).
 */

// ── Enums (mirrors app/models/enums.py) ───────────────────────────────────────

export type RequestStatus =
  | "new"
  | "viewed"
  | "in_progress"
  | "offer_sent"
  | "matched"
  | "closed"
  | "cancelled";

export type PriceBasis =
  | "unknown"
  | "EXW"
  | "FCA"
  | "FAS"
  | "FOB"
  | "CFR"
  | "CIF"
  | "CPT"
  | "CIP"
  | "DAP"
  | "DPU"
  | "DDP";

export type Urgency = "low" | "medium" | "high";

// ── Request creation (mirrors RequestCreate) ───────────────────────────────────

export interface RequestCreate {
  product_id?: number | null;       // null when a free-typed product is used
  product_text?: string | null;     // free-typed product name (not in catalog)
  grade_text?: string | null;
  polymer_type?: string | null;
  volume: number;
  volume_unit?: string;
  target_price?: number | null;
  currency?: string;
  incoterms?: PriceBasis;
  destination_country?: string;
  port_or_city?: string | null;
  desired_date?: string | null; // ISO date string YYYY-MM-DD
  validity_days?: number;
  urgency?: Urgency;
  comment?: string | null;
  // Contact step (IMG_0046) — snapshot onto the request
  company_name?: string | null;
  contact_name?: string | null;
  phone?: string | null;
  legal_address?: string | null;
}

// ── Request read-side (mirrors RequestOut) ─────────────────────────────────────

export interface RequestOut {
  id: number;
  number: string;
  status: RequestStatus;
  created_at: string; // ISO datetime string
}

// ── File metadata (mirrors RequestFileOut) ─────────────────────────────────────

export interface RequestFileMeta {
  id: number;
  file_name: string;
  mime_type: string | null;
  size_bytes: number | null;
}

// ── Status history (mirrors StatusHistoryOut) ──────────────────────────────────

export interface StatusHistory {
  from_status: RequestStatus | null;
  to_status: RequestStatus;
  created_at: string; // ISO datetime string
}

// ── Request detail (mirrors RequestDetailOut) ──────────────────────────────────

export interface RequestDetail extends RequestOut {
  product_id: number | null;
  product_text: string | null;
  grade_text: string | null;
  polymer_type: string | null;
  volume: number;
  volume_unit: string;
  target_price: number | null;
  currency: string;
  incoterms: PriceBasis;
  destination_country: string;
  port_or_city: string | null;
  desired_date: string | null; // ISO date string YYYY-MM-DD
  validity_days: number;
  urgency: Urgency;
  comment: string | null;
  company_name: string | null;
  contact_name: string | null;
  phone: string | null;
  legal_address: string | null;
  files: RequestFileMeta[];
  history: StatusHistory[];
}

// ── Client profile (mirrors ClientProfileOut / ClientProfilePatch) ─────────────

export interface ClientProfile {
  id: number;
  language: string;
  company_name: string | null;
  contact_name: string | null;
}

export interface ClientProfilePatch {
  language?: string;
  company_name?: string;
  contact_name?: string;
}
