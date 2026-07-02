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

// ── Reference data (mirrors ProductOut) ────────────────────────────────────────

export interface Product {
  id: number;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  name_tr: string | null;
  category: string;
  sort_order: number;
  is_active: boolean;
}

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

// ── Marketplace (Phase 2) ──────────────────────────────────────────────────────

export type SellerOfferStatus =
  | "draft"
  | "pending_moderation"
  | "approved"
  | "rejected"
  | "archived";

export type OfferFileKind = "image" | "tds" | "certificate" | "other";

export interface OfferFileRef {
  id: number;
  kind: OfferFileKind;
  file_name: string;
}

export interface CatalogSeller {
  company_name: string | null;
  contact_name: string | null;
  phone: string | null;
  telegram_username: string | null;
  is_verified: boolean;
}

export interface CatalogOffer {
  id: number;
  product_id: number | null;
  product_text: string | null;
  grade_text: string | null;
  polymer_type: string | null;
  qty_available: number;
  qty_unit: string;
  price: number;
  currency: string;
  incoterms: PriceBasis;
  warehouse_city: string | null;
  country: string | null;
  min_order_qty: number | null;
  description: string | null;
  published_at: string | null;
  files: OfferFileRef[];
  seller: CatalogSeller;
}

export interface CategoryCount {
  code: string;
  count: number;
}

export interface SellerOfferCreate {
  product_id?: number | null;
  product_text?: string | null;
  grade_text?: string | null;
  polymer_type?: string | null;
  qty_available: number;
  qty_unit?: string;
  price: number;
  currency?: string;
  incoterms?: PriceBasis;
  warehouse_city?: string | null;
  country?: string | null;
  min_order_qty?: number | null;
  description?: string | null;
  company_name?: string | null;
  contact_name?: string | null;
  phone?: string | null;
  telegram_username?: string | null;
}

// ── Browser auth (Telegram Login Widget) ───────────────────────────────────────

export interface AuthConfig {
  bot_username: string;
  login_ttl: number;
}

/** Payload produced by the Telegram Login Widget JS callback (window.Telegram.Login). */
export interface TelegramLoginPayload {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
  [key: string]: unknown;
}

/** Public landing offer — mirrors backend PublicFeaturedOffer (NO seller contact). */
export interface FeaturedOffer {
  id: number;
  product_id: number | null;
  product_text: string | null;
  grade_text: string | null;
  polymer_type: string | null;
  qty_available: number;
  qty_unit: string;
  price: number;
  currency: string;
  incoterms: PriceBasis;
  warehouse_city: string | null;
  country: string | null;
  published_at: string | null;
  files: OfferFileRef[];
}

export interface NewsSummary {
  id: number;
  title: string;
  period_start: string;
  period_end: string;
  published_at: string | null;
}

export interface NewsItem extends NewsSummary {
  content_md: string;
}

export interface SellerOfferOut {
  id: number;
  status: SellerOfferStatus;
  product_id: number | null;
  product_text: string | null;
  grade_text: string | null;
  polymer_type: string | null;
  qty_available: number;
  qty_unit: string;
  price: number;
  currency: string;
  incoterms: PriceBasis;
  warehouse_city: string | null;
  country: string | null;
  min_order_qty: number | null;
  description: string | null;
  moderation_note: string | null;
  files: OfferFileRef[];
  created_at: string;
}
