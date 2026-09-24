import type { TechnologistCard } from "@/entities/technologist";

/**
 * A factory's «нужен технолог» (0055), and everything hanging off it: offers,
 * threads, the closing review. Two readers see different shapes of the same
 * row — the factory reads `TechRequest`, an expert reads `TechFeedItem`, which
 * hides the factory until the two are talking.
 */

export type TechRequestStatus = "open" | "assigned" | "completed" | "cancelled";
export type TechOfferStatus = "submitted" | "accepted" | "declined" | "withdrawn";

export interface TechRequestInput {
  need_type: string;
  process: string;
  equipment: string;
  equipment_model: string | null;
  product: string;
  current_material: string | null;
  target_material: string | null;
  problem: string;
  capacity: string | null;
  capacity_unit: string | null;
  country: string;
  city: string | null;
  urgency: string;
  needed_by: string | null;
  work_format: string;
  languages: string[];
  budget_note: string | null;
}

interface TechRequestFields {
  id: number;
  number: string;
  need_type: string;
  process: string;
  equipment: string;
  equipment_model: string | null;
  product: string;
  current_material: string | null;
  target_material: string | null;
  problem: string;
  capacity: string | null;
  capacity_unit: string | null;
  country: string;
  city: string | null;
  urgency: string;
  needed_by: string | null;
  work_format: string;
  languages: string[];
  budget_note: string | null;
  status: TechRequestStatus;
  created_at: string;
}

/** The factory's own view. */
export interface TechRequest extends TechRequestFields {
  company_id: number;
  source: "form" | "ai";
  assigned_offer_id: number | null;
  offer_count: number;
  completed_at: string | null;
  cancelled_at: string | null;
}

export interface Contacts {
  name: string | null;
  phone: string | null;
  email: string | null;
}

export interface TechOffer {
  id: number;
  request_id: number;
  profile_id: number;
  scope: string;
  price: string;
  currency: string;
  duration_days: number;
  work_format: string;
  status: TechOfferStatus;
  created_at: string;
  updated_at: string;
}

export interface TechOfferInput {
  scope: string;
  price: string;
  currency: string;
  duration_days: number;
  work_format: string;
}

/** An expert's view: the factory is null until a thread exists. */
export interface TechFeedItem extends TechRequestFields {
  company: { id: number; name: string | null } | null;
  invited: boolean;
  my_offer: TechOffer | null;
  my_thread_id: number | null;
  /** The factory's contact — only once THIS expert's offer was accepted. */
  contacts: Contacts | null;
}

/** An offer as the factory reads it. */
export interface CompanyOffer extends TechOffer {
  technologist: TechnologistCard;
  thread_id: number | null;
  contacts: Contacts | null;
}

export interface TechThread {
  id: number;
  request_id: number;
  request_number: string;
  profile_id: number;
  my_side: "company" | "technologist";
  counterparty_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface TechReview {
  id: number;
  request_id: number;
  profile_id: number;
  rating: number;
  text: string | null;
  created_at: string;
}

/**
 * A thread line — the shape `features/thread-chat` renders, declared here
 * because an entity may not import a feature. `mine` is resolved by the server:
 * one side of this thread is a person, with no company id to compare.
 */
export interface TechMessage {
  id: number;
  author_kind: "company" | "technologist";
  author_company_id: number;
  mine: boolean;
  body: string;
  has_file: boolean;
  file_name: string | null;
  created_at: string;
}
