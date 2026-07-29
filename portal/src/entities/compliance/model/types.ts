/** Chemical compliance (P5): the substance registry, verdicts and licences. */

export type RegulationLevel = "free" | "docs_required" | "license_required" | "prohibited";

export type RegulationRegime =
  | "precursor_list_iv"
  | "explosive_toxic"
  | "strong_acting"
  | "pkm916_import";

/** A registry row as the seller's picker sees it. */
export interface SubstanceBrief {
  id: number;
  code: string;
  name_ru: string;
  name_uz: string | null;
  name_en: string | null;
  hs_code: string;
  cas: string | null;
  regulation_level: RegulationLevel;
  regulation_regime: RegulationRegime | null;
  /** Below this the regime does not apply (string — a threshold is exact). */
  threshold_concentration_pct: string | null;
  required_docs: string[];
}

/** One thing standing between an offer and publication. */
export interface MissingRequirement {
  /** "document" | "license" | "prohibited" */
  kind: string;
  /** A document kind, a regime, or the act that bans it. */
  detail: string | null;
}

/** What publishing an offer requires right now. */
export interface OfferCompliance {
  ok: boolean;
  level: RegulationLevel;
  regime: RegulationRegime | null;
  exempt_reason: string | null;
  missing: MissingRequirement[];
  substance: SubstanceBrief | null;
  /** False while `dangerous_check_enforced` is off — nothing is actually blocked. */
  enforced: boolean;
  checked_at: string | null;
}

export interface CompanyLicense {
  id: number;
  company_id: number;
  regime: RegulationRegime;
  category: string | null;
  license_number: string | null;
  issued_by: string | null;
  issued_at: string | null;
  expires_at: string | null;
  status: "pending_review" | "active" | "expired" | "revoked" | "rejected";
  revoked_at: string | null;
  revoke_reason: string | null;
  note: string | null;
  created_at: string;
  /** Whether it covers today — status alone does not say (expiry is a date). */
  is_active: boolean;
}

/** A journalled AI hint the seller has not answered yet. */
export interface SubstanceSuggestion {
  id: number;
  offer_id: number | null;
  suggested_name: string | null;
  suggested_cas: string | null;
  suggested_hs_code: string | null;
  suggested_concentration_pct: string | null;
  confidence: string | null;
  substance: SubstanceBrief | null;
  accepted: boolean | null;
  created_at: string;
}
