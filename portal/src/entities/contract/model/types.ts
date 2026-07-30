export interface ContractTemplate {
  id: number;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  version: number;
  variables_schema: Record<string, unknown>;
}

export interface ContractSignature {
  company_id: number;
  company_name: string | null;
  signed_at: string;
}

export interface ContractSummary {
  id: number;
  public_id: string;
  title: string;
  status: string;
  template_code: string | null;
  initiator_company_id: number;
  initiator_name: string | null;
  counterparty_company_id: number;
  counterparty_name: string | null;
  role: "initiator" | "counterparty";
  offer_id: number | null;
  created_at: string;
  sent_at: string | null;
  activated_at: string | null;
}

export interface ContractDetail extends ContractSummary {
  variables: Record<string, unknown>;
  declined_reason: string | null;
  document_available: boolean;
  document_sha256: string | null;
  signatures: ContractSignature[];
}

export interface DirectoryCompany {
  id: number;
  public_id: string;
  legal_name: string | null;
  tax_id: string;
  roles: string[];
  verified: boolean;
}

export interface CreateContractPayload {
  initiator_company_id: number;
  counterparty_company_id: number;
  template_id: number;
  variables: Record<string, unknown>;
  offer_id?: number | null;
  title?: string;
}
