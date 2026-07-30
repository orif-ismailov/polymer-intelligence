/**
 * Manufacturers directory + factory RFQ + buyer↔manufacturer chat domain
 * (`docs/new-design/manufacturer_flow.jpeg`).
 *
 * Money/quantity fields are strings end to end — they are contract terms, and a
 * float round-trip is a wrong number. Format for display, never parse to Number
 * for arithmetic.
 */

export interface ManufacturerCard {
  id: number;
  public_id: string;
  legal_name: string | null;
  short_name: string | null;
  legal_address: string | null;
  jurisdiction: string;
  logo_url: string | null;
  verified_at: string | null;
  offer_count: number;
  /** Subset of `companies.manufacturer_profile` safe for the directory card. */
  production_type: string | null;
  main_products: string | null;
  employees: number | null;
  founded_year: number | null;
  export_countries: string[];
  iso_certification: string | null;
}

export interface ManufacturerList {
  items: ManufacturerCard[];
  total: number;
  limit: number;
  offset: number;
}

export const FACTORY_RFQ_DOC_KINDS = [
  "founding_docs",
  "registration_certificate",
  "tax_id",
  "bank_details",
  "import_export_license",
] as const;
export type FactoryRfqDocumentKind = (typeof FACTORY_RFQ_DOC_KINDS)[number];

export interface FactoryRfqDocument {
  id: number;
  kind: FactoryRfqDocumentKind;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
}

/** Body for `POST /portal/manufacturers/{id}/rfqs`. */
export interface FactoryRfqCreatePayload {
  company_id: number;
  offer_id: number;
  quantity: string;
  qty_unit?: string;
  target_price?: string | null;
  currency?: string;
  incoterms?: string | null;
  destination_port?: string | null;
  desired_delivery_date?: string | null;
  payment_method?: string | null;
  offer_validity?: string | null;
  performance_guarantee?: string | null;
  inspection_requirement?: string | null;
  additional_requirements?: string | null;
  contact_name: string;
  contact_position?: string | null;
  contact_email?: string | null;
  contact_phone: string;
  contact_telegram?: string | null;
}

export interface FactoryRfq {
  id: number;
  public_id: string;
  number: string;
  buyer_company_id: number;
  manufacturer_company_id: number;
  offer_id: number;
  offer_title: string | null;
  manufacturer_name: string | null;
  quantity: string;
  qty_unit: string;
  target_price: string | null;
  currency: string;
  incoterms: string | null;
  destination_port: string | null;
  desired_delivery_date: string | null;
  payment_method: string | null;
  offer_validity: string | null;
  performance_guarantee: string | null;
  inspection_requirement: string | null;
  additional_requirements: string | null;
  contact_name: string;
  contact_position: string | null;
  contact_email: string | null;
  contact_phone: string;
  contact_telegram: string | null;
  status: string;
  documents: FactoryRfqDocument[];
  created_at: string;
}

export interface ManufacturerThread {
  id: number;
  buyer_company_id: number;
  manufacturer_company_id: number;
  counterparty_name: string | null;
  my_role: "buyer" | "manufacturer";
  created_at: string;
  updated_at: string;
}

export interface ManufacturerMessage {
  id: number;
  thread_id: number;
  author_account_id: number;
  author_company_id: number;
  body: string;
  file_name: string | null;
  has_file: boolean;
  created_at: string;
}

export interface ManufacturerMessagePage {
  items: ManufacturerMessage[];
  last_id: number | null;
}
