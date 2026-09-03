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
  /**
   * Which rail carries the signatures.
   *
   * On `didox` the parties sign a document held by the EDI operator, so
   * `signatures` stays empty by design — we never see the counterparty's PKCS#7,
   * they may have signed at any of the 27 operators.
   */
  signing_provider?: "eimzo" | "didox";
  didox_document_id?: number | null;
  /** Didox's ladder verbatim: 0 draft · 1 awaiting partner · 3 signed · 4 rejected · 50 annulled. */
  didox_status?: number | null;
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
  /**
   * Which rail carries the signatures, frozen at creation.
   *
   * `eimzo` — both sides sign a PDF we hold and we verify the PKCS#7 ourselves.
   * `didox` — the document lives at the EDI operator, which is what puts it in
   * front of the tax authority; it needs a Didox account on BOTH sides, so it is
   * opt-in and never the default.
   */
  signing_provider?: "eimzo" | "didox";
  /**
   * The deal this contract belongs to.
   *
   * `DealDetailPage` has always passed `?deal_id=` and this page silently dropped
   * it, so `deals.contract_id` stayed NULL and the deal never advanced past
   * `contract_pending` — no `contract_signed`, no escrow.
   */
  deal_id?: number | null;
}
