import type { CompanyStatus } from "@/shared/config";
import type { CaseOut } from "@/entities/verification";

export interface CompanyRole {
  role: string;
  status: string;
}

export interface BankAccount {
  id: number;
  bank_mfo: string;
  bank_name: string | null;
  account_masked: string;
  currency: string;
  status: string;
}

export interface DocumentMeta {
  id: number;
  kind: string;
  mime_type: string | null;
  size_bytes: number | null;
  status: string;
  created_at: string;
}

export interface CompanySummary {
  id: number;
  public_id: string;
  jurisdiction: string;
  tax_id: string;
  legal_name: string | null;
  short_name: string | null;
  status: CompanyStatus;
  verified_at: string | null;
  active_case: CaseOut | null;
}

export interface CompanyDetail extends CompanySummary {
  legal_form: string | null;
  legal_address: string | null;
  actual_address: string | null;
  registration_number: string | null;
  director_name: string | null;
  /** ISO `yyyy-mm-dd` — the date on the registration certificate. */
  registration_date: string | null;
  manufacturer_profile: ManufacturerProfile | null;
  logistics_profile: LogisticsProfile | null;
  laboratory_profile: LaboratoryProfile | null;
  identity_locked: boolean;
  reverification_due_at: string | null;
  roles: CompanyRole[];
  bank_accounts: BankAccount[];
  documents: DocumentMeta[];
  case: CaseOut | null;
}

export interface ManufacturerProfile {
  production_type?: string | null;
  main_products?: string | null;
  annual_capacity_tons?: number | null;
  production_lines?: number | null;
  employees?: number | null;
  markets?: string[];
  export_countries?: string[];
  founded_year?: number | null;
  iso_certification?: string | null;
  moq_tons?: number | null;
  min_annual_volume_tons?: number | null;
  financial_requirements?: Record<string, boolean>;
  additional_requirements?: string[];
  additional_other?: string | null;
}

export interface LogisticsProfile {
  city?: string | null;
  services?: string[];
  from_countries?: string[];
  to_countries?: string[];
  popular_routes?: string[];
  cargo_types?: string[];
  capabilities?: string[];
  tariff_model?: string | null;
}

export interface LaboratoryProfile {
  city?: string | null;
  website?: string | null;
  email?: string | null;
  phone?: string | null;
  description?: string | null;
}

export interface CreateCompanyPayload {
  jurisdiction?: string;
  tax_id: string;
}

export interface CompanyProfilePatch {
  legal_name?: string;
  short_name?: string;
  legal_form?: string;
  legal_address?: string;
  actual_address?: string;
  registration_number?: string;
  director_name?: string;
  /** ISO `yyyy-mm-dd`. */
  registration_date?: string;
  manufacturer_profile?: ManufacturerProfile;
  logistics_profile?: LogisticsProfile;
  laboratory_profile?: LaboratoryProfile;
}

export interface CreateBankAccountPayload {
  bank_mfo: string;
  account_number: string;
  bank_name?: string;
  currency?: string;
}
