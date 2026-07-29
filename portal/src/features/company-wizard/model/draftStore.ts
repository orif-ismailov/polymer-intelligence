import { create } from "zustand";

import { DEFAULT_JURISDICTION } from "./constants";

export interface WizardIdentity {
  jurisdiction: string;
  tax_id: string;
  legal_name: string;
  legal_form: string;
  legal_address: string;
  director_name: string;
}

export interface WizardBank {
  enabled: boolean;
  bank_mfo: string;
  account_number: string;
  bank_name: string;
  currency: string;
}

/** A staged document: kind → the File the user selected (not yet uploaded). */
export type WizardDocuments = Record<string, File | null>;

interface WizardDraftState {
  identity: WizardIdentity;
  roles: string[];
  bank: WizardBank;
  documents: WizardDocuments;
  setIdentity: (patch: Partial<WizardIdentity>) => void;
  toggleRole: (role: string) => void;
  setBank: (patch: Partial<WizardBank>) => void;
  setDocument: (kind: string, file: File | null) => void;
  reset: () => void;
}

const emptyIdentity: WizardIdentity = {
  jurisdiction: DEFAULT_JURISDICTION,
  tax_id: "",
  legal_name: "",
  legal_form: "",
  legal_address: "",
  director_name: "",
};

const emptyBank: WizardBank = {
  enabled: false,
  bank_mfo: "",
  account_number: "",
  bank_name: "",
  currency: "UZS",
};

export const useWizardDraft = create<WizardDraftState>((set) => ({
  identity: { ...emptyIdentity },
  roles: [],
  bank: { ...emptyBank },
  documents: {},
  setIdentity: (patch) => set((s) => ({ identity: { ...s.identity, ...patch } })),
  toggleRole: (role) =>
    set((s) => ({
      roles: s.roles.includes(role) ? s.roles.filter((r) => r !== role) : [...s.roles, role],
    })),
  setBank: (patch) => set((s) => ({ bank: { ...s.bank, ...patch } })),
  setDocument: (kind, file) => set((s) => ({ documents: { ...s.documents, [kind]: file } })),
  reset: () =>
    set({ identity: { ...emptyIdentity }, roles: [], bank: { ...emptyBank }, documents: {} }),
}));
