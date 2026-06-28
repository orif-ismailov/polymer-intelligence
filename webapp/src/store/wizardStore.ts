/**
 * Zustand wizard store — client-only, no server persistence (D-01).
 *
 * State survives minimize (zustand in-memory persists across the Web App
 * lifecycle). The wizard collects fields across 4 steps; they are submitted
 * to the API only when the user taps "Отправить" on Step 4 (→ Confirm).
 *
 * 5-step buyer flow (IMG_0046): product → delivery terms → contact →
 * additional → confirm/success.
 *
 * D-01 invariant: no fetch/API call inside this store.
 */

import { create } from "zustand";

// ── Store interface ────────────────────────────────────────────────────────────

export interface WizardState {
  // Current step (1 | 2 | 3 | 4)
  step: 1 | 2 | 3 | 4;

  // Step 1: product/grade/volume. product_id OR product_text is required.
  product_id: number | null;
  product_text: string;   // free-typed product when not in the catalog
  grade_text: string;
  polymer_type: string;
  volume: string;       // kept as string for the input; converted to number on submit
  volume_unit: string;

  // Step 2: delivery terms
  port_or_city: string;
  desired_date: string; // ISO date string or ""
  urgency: string;      // "low" | "medium" | "high"
  // carried with defaults (not collected in the UI) but still submitted
  target_price: string; // string for input, convert on submit
  currency: string;
  incoterms: string;
  destination_country: string;
  validity_days: string;

  // Step 3: contact (snapshot onto the request)
  company_name: string;
  contact_name: string;
  phone: string;
  legal_address: string;

  // Step 4: comment + files
  comment: string;
  files: File[];

  // Actions
  setField<
    K extends keyof Omit<
      WizardState,
      "files" | "nextStep" | "prevStep" | "reset" | "setField" | "setFiles"
    >,
  >(
    key: K,
    value: WizardState[K],
  ): void;
  setFiles(files: File[]): void;
  nextStep(): void;
  prevStep(): void;
  reset(): void;
}

// ── Initial state ──────────────────────────────────────────────────────────────

const INITIAL_STATE = {
  step: 1 as const,
  // Step 1
  product_id: null,
  product_text: "",
  grade_text: "",
  polymer_type: "",
  volume: "",
  volume_unit: "MT",
  // Step 2
  port_or_city: "",
  desired_date: "",
  urgency: "medium",
  target_price: "",
  currency: "USD",
  incoterms: "unknown",
  destination_country: "UZ",
  validity_days: "30",
  // Step 3
  company_name: "",
  contact_name: "",
  phone: "",
  legal_address: "",
  // Step 4
  comment: "",
  files: [] as File[],
};

// ── Store ──────────────────────────────────────────────────────────────────────

export const useWizardStore = create<WizardState>((set) => ({
  ...INITIAL_STATE,

  setField: (key, value) => set({ [key]: value } as Partial<WizardState>),

  setFiles: (files: File[]) => set({ files }),

  nextStep: () => set((s) => ({ step: Math.min(4, s.step + 1) as 1 | 2 | 3 | 4 })),

  prevStep: () => set((s) => ({ step: Math.max(1, s.step - 1) as 1 | 2 | 3 | 4 })),

  reset: () => set({ ...INITIAL_STATE, files: [] }),
}));
