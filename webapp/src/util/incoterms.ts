/**
 * Incoterms® 2020 reference data — the structural facts of each delivery term.
 *
 * The responsibility matrix (who clears customs, who pays carriage, who insures,
 * where risk transfers) is a published standard, not copy — so it lives here as
 * data, keyed by term. Only the human-readable prose (plain-language summary and
 * the risk-transfer phrasing) is translated, via i18n keys under `incotermsGuide`.
 *
 * `INCOTERM_CODES` is the ordered, selectable set for the seller forms — ordered by
 * increasing seller obligation (EXW = buyer does everything → DDP = seller does everything),
 * so tapping left→right tells a coherent story.
 *
 * Shared by SellOffer (create), EditOffer (edit) and the IncotermsGuide modal.
 */

/** Which side carries a given responsibility. `you` = the seller filling in the form. */
export type Party = "you" | "buyer";

/** Where transit risk passes from seller to buyer — one of five standard moments. */
export type RiskPoint = "premises" | "carrier" | "onboard" | "destination" | "destinationUnloaded";

export interface IncotermInfo {
  code: string;
  /** Standardised English name (Incoterms® names are not localised). */
  fullName: string;
  /** Export (origin) customs clearance. */
  exportClearance: Party;
  /** Main-carriage transport cost to the agreed destination. */
  mainTransport: Party;
  /** Who carries the transit risk and should therefore insure the cargo. */
  insurance: Party;
  /** Import (destination) customs clearance and duties. */
  importClearance: Party;
  /** The moment risk passes to the buyer. */
  riskAt: RiskPoint;
}

/** Ordered, selectable Incoterms for the seller forms (increasing seller obligation). */
export const INCOTERM_CODES = ["EXW", "FCA", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"] as const;

export type IncotermCode = (typeof INCOTERM_CODES)[number];

const TERMS: Record<IncotermCode, IncotermInfo> = {
  EXW: { code: "EXW", fullName: "Ex Works", exportClearance: "buyer", mainTransport: "buyer", insurance: "buyer", importClearance: "buyer", riskAt: "premises" },
  FCA: { code: "FCA", fullName: "Free Carrier", exportClearance: "you", mainTransport: "buyer", insurance: "buyer", importClearance: "buyer", riskAt: "carrier" },
  FOB: { code: "FOB", fullName: "Free On Board", exportClearance: "you", mainTransport: "buyer", insurance: "buyer", importClearance: "buyer", riskAt: "onboard" },
  CFR: { code: "CFR", fullName: "Cost and Freight", exportClearance: "you", mainTransport: "you", insurance: "buyer", importClearance: "buyer", riskAt: "onboard" },
  CIF: { code: "CIF", fullName: "Cost, Insurance and Freight", exportClearance: "you", mainTransport: "you", insurance: "you", importClearance: "buyer", riskAt: "onboard" },
  CPT: { code: "CPT", fullName: "Carriage Paid To", exportClearance: "you", mainTransport: "you", insurance: "buyer", importClearance: "buyer", riskAt: "carrier" },
  CIP: { code: "CIP", fullName: "Carriage and Insurance Paid To", exportClearance: "you", mainTransport: "you", insurance: "you", importClearance: "buyer", riskAt: "carrier" },
  DAP: { code: "DAP", fullName: "Delivered at Place", exportClearance: "you", mainTransport: "you", insurance: "you", importClearance: "buyer", riskAt: "destination" },
  DPU: { code: "DPU", fullName: "Delivered at Place Unloaded", exportClearance: "you", mainTransport: "you", insurance: "you", importClearance: "buyer", riskAt: "destinationUnloaded" },
  DDP: { code: "DDP", fullName: "Delivered Duty Paid", exportClearance: "you", mainTransport: "you", insurance: "you", importClearance: "you", riskAt: "destination" },
};

/** Ordered list of full term info, for rendering the guide. */
export const INCOTERMS: readonly IncotermInfo[] = INCOTERM_CODES.map((c) => TERMS[c]);

/** Look up one term; returns undefined for unknown/blank codes (e.g. "unknown", "FAS"). */
export function getIncoterm(code: string | null | undefined): IncotermInfo | undefined {
  return INCOTERMS.find((t) => t.code === code);
}

/** The four responsibility rows shown per term, in display order. */
export const RESPONSIBILITY_ROWS = [
  { key: "exportClearance", labelKey: "incotermsGuide.cols.export" },
  { key: "mainTransport", labelKey: "incotermsGuide.cols.transport" },
  { key: "insurance", labelKey: "incotermsGuide.cols.insurance" },
  { key: "importClearance", labelKey: "incotermsGuide.cols.import" },
] as const;
