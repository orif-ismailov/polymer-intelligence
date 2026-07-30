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
  director_name: string | null;
  /** ISO `yyyy-mm-dd` — the date on the registration certificate. */
  registration_date: string | null;
  identity_locked: boolean;
  reverification_due_at: string | null;
  roles: CompanyRole[];
  bank_accounts: BankAccount[];
  documents: DocumentMeta[];
  case: CaseOut | null;
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
  director_name?: string;
  /** ISO `yyyy-mm-dd`. */
  registration_date?: string;
}

export interface CreateBankAccountPayload {
  bank_mfo: string;
  account_number: string;
  bank_name?: string;
  currency?: string;
}
