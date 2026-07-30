import { create } from "zustand";

import type { FactoryRfqCreatePayload, FactoryRfqDocumentKind } from "@/entities/manufacturer";

import { DEFAULT_CURRENCY, DEFAULT_QTY_UNIT } from "./constants";

export interface FactoryRfqDraft {
  // ── 1. Basic terms ─────────────────────────────────────────────────────
  quantity: string;
  qtyUnit: string;
  targetPrice: string;
  currency: string;
  incoterms: string;
  destinationPort: string;
  desiredDeliveryDate: string;
  // ── 2. Documents (kept as Files — uploaded after the RFQ row exists) ────
  documents: Partial<Record<FactoryRfqDocumentKind, File>>;
  // ── 3. Commercial terms ──────────────────────────────────────────────────
  paymentMethod: string;
  offerValidity: string;
  performanceGuarantee: string;
  inspectionRequirement: string;
  additionalRequirements: string;
  // ── 4. Contact ────────────────────────────────────────────────────────
  contactName: string;
  contactPosition: string;
  contactEmail: string;
  contactPhone: string;
  contactTelegram: string;
}

interface FactoryRfqState {
  draft: FactoryRfqDraft;
  setField: <K extends keyof FactoryRfqDraft>(key: K, value: FactoryRfqDraft[K]) => void;
  setDocument: (kind: FactoryRfqDocumentKind, file: File | null) => void;
  begin: (seed?: Partial<FactoryRfqDraft>) => void;
  reset: () => void;
  toPayload: (companyId: number, offerId: number) => FactoryRfqCreatePayload;
}

const EMPTY: FactoryRfqDraft = {
  quantity: "",
  qtyUnit: DEFAULT_QTY_UNIT,
  targetPrice: "",
  currency: DEFAULT_CURRENCY,
  incoterms: "",
  destinationPort: "",
  desiredDeliveryDate: "",
  documents: {},
  paymentMethod: "",
  offerValidity: "",
  performanceGuarantee: "",
  inspectionRequirement: "",
  additionalRequirements: "",
  contactName: "",
  contactPosition: "",
  contactEmail: "",
  contactPhone: "",
  contactTelegram: "",
};

export const useFactoryRfqDraft = create<FactoryRfqState>((set, get) => ({
  draft: { ...EMPTY },

  setField: (key, value) => set((s) => ({ draft: { ...s.draft, [key]: value } })),

  setDocument: (kind, file) =>
    set((s) => {
      const documents = { ...s.draft.documents };
      if (file) documents[kind] = file;
      else delete documents[kind];
      return { draft: { ...s.draft, documents } };
    }),

  begin: (seed) => set({ draft: { ...EMPTY, ...seed } }),

  reset: () => set({ draft: { ...EMPTY } }),

  toPayload: (companyId, offerId) => {
    const { draft } = get();
    return {
      company_id: companyId,
      offer_id: offerId,
      quantity: draft.quantity.trim(),
      qty_unit: draft.qtyUnit || DEFAULT_QTY_UNIT,
      target_price: draft.targetPrice.trim() || null,
      currency: draft.currency || DEFAULT_CURRENCY,
      incoterms: draft.incoterms.trim() || null,
      destination_port: draft.destinationPort.trim() || null,
      desired_delivery_date: draft.desiredDeliveryDate || null,
      payment_method: draft.paymentMethod.trim() || null,
      offer_validity: draft.offerValidity.trim() || null,
      performance_guarantee: draft.performanceGuarantee.trim() || null,
      inspection_requirement: draft.inspectionRequirement.trim() || null,
      additional_requirements: draft.additionalRequirements.trim() || null,
      contact_name: draft.contactName.trim(),
      contact_position: draft.contactPosition.trim() || null,
      contact_email: draft.contactEmail.trim() || null,
      contact_phone: draft.contactPhone.trim(),
      contact_telegram: draft.contactTelegram.trim() || null,
    };
  },
}));

/** Sheet 1 — positive quantity is the only hard requirement. */
export function isBasicValid(draft: FactoryRfqDraft): boolean {
  return Number(draft.quantity) > 0;
}

/** Sheet 4 — the backend requires a name and a phone. */
export function isContactValid(draft: FactoryRfqDraft): boolean {
  return draft.contactName.trim() !== "" && draft.contactPhone.trim() !== "";
}
