/**
 * Zustand wizard store — client-only, no server persistence (D-01).
 *
 * State survives minimize (zustand in-memory persists across the Web App
 * lifecycle). The wizard collects fields across 3 steps; they are submitted
 * to the API only when the user taps "Отправить" on Step 3.
 *
 * D-01 invariant: no fetch/API call inside this store.
 */

import { create } from "zustand";

// ── Store interface ────────────────────────────────────────────────────────────

export interface WizardState {
  // Current step (1 | 2 | 3)
  step: 1 | 2 | 3;

  // Step 1: product/grade/volume (D-02 minimum required fields)
  product_id: number | null;
  grade_text: string;
  polymer_type: string;
  volume: string;       // kept as string for the input; converted to number on submit
  volume_unit: string;

  // Step 2: delivery terms (all optional per D-02)
  target_price: string; // string for input, convert on submit
  currency: string;
  incoterms: string;
  destination_country: string;
  port_or_city: string;
  desired_date: string; // ISO date string or ""
  validity_days: string; // string for input, default "30"

  // Step 3: comment + files
  comment: string;
  files: File[];

  // Actions
  setField<K extends keyof Omit<WizardState, "files" | "step" | "nextStep" | "prevStep" | "reset" | "setField" | "setFiles">>(
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
  grade_text: "",
  polymer_type: "",
  volume: "",
  volume_unit: "MT",
  // Step 2
  target_price: "",
  currency: "USD",
  incoterms: "unknown",
  destination_country: "UZ",
  port_or_city: "",
  desired_date: "",
  validity_days: "30",
  // Step 3
  comment: "",
  files: [] as File[],
};

// ── Store ──────────────────────────────────────────────────────────────────────

export const useWizardStore = create<WizardState>((set) => ({
  ...INITIAL_STATE,

  setField: (key, value) => set({ [key]: value } as Partial<WizardState>),

  setFiles: (files: File[]) => set({ files }),

  nextStep: () =>
    set((s) => ({ step: Math.min(3, s.step + 1) as 1 | 2 | 3 })),

  prevStep: () =>
    set((s) => ({ step: Math.max(1, s.step - 1) as 1 | 2 | 3 })),

  reset: () => set({ ...INITIAL_STATE, files: [] }),
}));
