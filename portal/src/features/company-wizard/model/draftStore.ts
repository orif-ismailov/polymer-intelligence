import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { CompanyDetail } from "@/entities/company";

import { DEFAULT_JURISDICTION } from "./constants";

export interface WizardIdentity {
  jurisdiction: string;
  tax_id: string;
  legal_name: string;
  legal_form: string;
  legal_address: string;
  director_name: string;
  /** ISO `yyyy-mm-dd` — what `<input type="date">` reads and writes. */
  registration_date: string;
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
  /** One of `ACCOUNT_TYPES[].id`; "" until the user picks on step 1. */
  accountType: string;
  identity: WizardIdentity;
  bank: WizardBank;
  documents: WizardDocuments;
  /**
   * Set once step 1's E-IMZO signature creates the company: the row already
   * exists, so the review step patches it instead of creating a duplicate.
   */
  companyId: number | null;
  /** True after a successful signature — frozen requisites must not be PATCHed. */
  identityLocked: boolean;
  setAccountType: (id: string) => void;
  setIdentity: (patch: Partial<WizardIdentity>) => void;
  setBank: (patch: Partial<WizardBank>) => void;
  setDocument: (kind: string, file: File | null) => void;
  adoptCompany: (companyId: number, locked: boolean) => void;
  /** Copy server-side requisites over the draft (after an E-IMZO signature). */
  hydrateFromCompany: (company: CompanyDetail) => void;
  reset: () => void;
}

const emptyIdentity: WizardIdentity = {
  jurisdiction: DEFAULT_JURISDICTION,
  tax_id: "",
  legal_name: "",
  legal_form: "",
  legal_address: "",
  director_name: "",
  registration_date: "",
};

const emptyBank: WizardBank = {
  enabled: false,
  bank_mfo: "",
  account_number: "",
  bank_name: "",
  currency: "UZS",
};

/**
 * Registration is long enough that losing it to a stray reload is a real cost: the
 * store used to be plain in-memory state, so a refresh (or a crash, or a
 * back-navigation out of the flow) silently discarded every field the user had
 * typed and dropped them on the same step with a blank form.
 *
 * `documents` is deliberately NOT persisted — a `File` has no serialisable form,
 * and a filename without its bytes would be a lie the user only discovers at
 * upload time. Losing them is safe: the wizard's reachability guard sends the user
 * back to «Документы» to re-attach, which is exactly what needs to happen.
 */
const PERSIST_KEY = "imex.company-wizard.draft";

export const useWizardDraft = create<WizardDraftState>()(
  persist(
    (set) => ({
      accountType: "",
      identity: { ...emptyIdentity },
      bank: { ...emptyBank },
      documents: {},
      companyId: null,
      identityLocked: false,
      setAccountType: (id) => set({ accountType: id }),
      setIdentity: (patch) => set((s) => ({ identity: { ...s.identity, ...patch } })),
      setBank: (patch) => set((s) => ({ bank: { ...s.bank, ...patch } })),
      setDocument: (kind, file) => set((s) => ({ documents: { ...s.documents, [kind]: file } })),
      adoptCompany: (companyId, locked) => set({ companyId, identityLocked: locked }),
      hydrateFromCompany: (company) =>
        set((s) => ({
          companyId: company.id,
          identityLocked: company.identity_locked,
          identity: {
            ...s.identity,
            jurisdiction: company.jurisdiction,
            tax_id: company.tax_id,
            // The signature is the source of truth for the requisites it froze; for
            // everything else the server value only fills a blank the user has not
            // typed into, so hydrating never discards their input.
            legal_name: company.legal_name ?? s.identity.legal_name,
            director_name: company.director_name ?? s.identity.director_name,
            legal_form: s.identity.legal_form || (company.legal_form ?? ""),
            legal_address: s.identity.legal_address || (company.legal_address ?? ""),
            registration_date: s.identity.registration_date || (company.registration_date ?? ""),
          },
        })),
      reset: () =>
        set({
          accountType: "",
          identity: { ...emptyIdentity },
          bank: { ...emptyBank },
          documents: {},
          companyId: null,
          identityLocked: false,
        }),
    }),
    {
      name: PERSIST_KEY,
      // Files are not serialisable — see the note on PERSIST_KEY.
      partialize: (s) => ({
        accountType: s.accountType,
        identity: s.identity,
        bank: s.bank,
        companyId: s.companyId,
        identityLocked: s.identityLocked,
      }),
    },
  ),
);
