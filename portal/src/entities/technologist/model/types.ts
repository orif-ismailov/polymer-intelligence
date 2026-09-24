/**
 * The technologist marketplace (0055) — an expert's side.
 *
 * Three shapes, mirroring the API's three audiences: the public card (no
 * contacts, from the approved snapshot), the expert's own editor, and the
 * closed vocabularies every form and filter is built from.
 */

export type ProfileStatus =
  | "draft"
  | "pending_review"
  | "published"
  | "rejected"
  | "suspended";

/** The public card — catalog, profile page, a factory's offer list. */
export interface TechnologistCard {
  id: number;
  full_name: string | null;
  title: string | null;
  country: string | null;
  city: string | null;
  photo_url: string | null;
  years_experience: number | null;
  projects_count: number | null;
  countries_count: number | null;
  bio: string | null;
  industries: string[];
  processes: string[];
  materials: string[];
  equipment_brands: string[];
  work_formats: string[];
  languages: string[];
  /** Decimal as a string, e.g. "4.50"; null until the first review. */
  rating_avg: string | null;
  rating_count: number;
}

export interface TechnologistCardList {
  items: TechnologistCard[];
  total: number;
}

export interface TechnologistFilters {
  process?: string;
  material?: string;
  language?: string;
  country?: string;
  q?: string;
}

/** The expert's editor payload. Every field optional — a draft saves half-filled. */
export interface TechnologistProfileInput {
  full_name: string | null;
  title: string | null;
  country: string | null;
  city: string | null;
  years_experience: number | null;
  projects_count: number | null;
  countries_count: number | null;
  bio: string | null;
  industries: string[];
  processes: string[];
  materials: string[];
  equipment_brands: string[];
  work_formats: string[];
  languages: string[];
  contact_phone: string | null;
  contact_email: string | null;
}

export interface TechnologistOwnProfile extends TechnologistProfileInput {
  id: number;
  photo_url: string | null;
  status: ProfileStatus;
  rejection_reason: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  /** True while the catalog shows (an approved version of) this profile. */
  is_listed: boolean;
  /** What «Отправить на проверку» would be refused for. */
  missing_fields: string[];
  rating_avg: string | null;
  rating_count: number;
}

export interface TechFacets {
  industries: string[];
  processes: string[];
  materials: string[];
  need_types: string[];
  urgencies: string[];
  request_formats: string[];
  profile_formats: string[];
  capacity_units: string[];
  currencies: string[];
  languages: string[];
}
