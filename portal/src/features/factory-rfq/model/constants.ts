/**
 * The factory RFQ flow (`docs/new-design/manufacturer_flow.jpeg`).
 *
 * Four sheets — basic terms, compliance documents, commercial terms, contact —
 * then the created RFQ hands off to `/manufacturers/rfqs/:rfqId/done`.
 */

export const STEP_BASIC = 1;
export const STEP_DOCUMENTS = 2;
export const STEP_TERMS = 3;
export const STEP_CONTACT = 4;

export const FIRST_STEP = STEP_BASIC;
export const LAST_STEP = STEP_CONTACT;
export const COUNTED_STEPS = 4;

export { FACTORY_RFQ_DOC_KINDS } from "@/entities/manufacturer";
export type { FactoryRfqDocumentKind } from "@/entities/manufacturer";

/** Must mirror the backend `FactoryRfqCreateIn.qty_unit` default set. */
export const RFQ_QTY_UNITS = ["MT", "KG"] as const;

/** Must mirror the backend `FactoryRfqCreateIn.currency` (ISO-4217, 3 letters). */
export const RFQ_CURRENCIES = ["USD", "UZS", "EUR", "RUB"] as const;

/** Must mirror the backend `PriceBasis` enum verbatim. */
export const RFQ_INCOTERMS = ["EXW", "FCA", "FOB", "CIF", "CPT", "DAP", "DDP"] as const;

export const DEFAULT_QTY_UNIT = "MT";
export const DEFAULT_CURRENCY = "USD";
