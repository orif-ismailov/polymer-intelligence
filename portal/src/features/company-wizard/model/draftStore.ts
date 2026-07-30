import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { CompanyDetail } from "@/entities/company";

import {
  DEFAULT_JURISDICTION,
  type AdditionalRequirementKey,
  type FinancialRequirementKey,
  type LogisticsTariffModel,
  type MarketOption,
} from "./constants";

export interface WizardIdentity {
  jurisdiction: string;
  tax_id: string;
  legal_name: string;
  short_name: string;
  legal_form: string;
  legal_address: string;
  actual_address: string;
  registration_number: string;
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

export interface WizardManufacturerProfile {
  production_type: string;
  main_products: string;
  annual_capacity_tons: string;
  production_lines: string;
  employees: string;
  markets: MarketOption[];
  export_countries: string[];
  founded_year: string;
  iso_certification: string;
  moq_tons: string;
  min_annual_volume_tons: string;
  financial_requirements: Record<FinancialRequirementKey, boolean>;
  additional_requirements: AdditionalRequirementKey[];
  additional_other: string;
}

export interface WizardLogisticsProfile {
  city: string;
  services: string[];
  from_countries: string[];
  to_countries: string[];
  popular_routes: string[];
  cargo_types: string[];
  capabilities: string[];
  tariff_model: LogisticsTariffModel | "";
}

export interface WizardLaboratoryProfile {
  city: string;
  website: string;
  email: string;
  phone: string;
  description: string;
}

interface WizardDraftState {
  /** One of `ACCOUNT_TYPES[].id`; "" until the user picks on step 1. */
  accountType: string;
  identity: WizardIdentity;
  bank: WizardBank;
  documents: WizardDocuments;
  manufacturer: WizardManufacturerProfile;
  logistics: WizardLogisticsProfile;
  laboratory: WizardLaboratoryProfile;
  /** Staged logo file — not persisted (File is not serialisable). */
  logo: File | null;
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
  setManufacturer: (patch: Partial<WizardManufacturerProfile>) => void;
  setLogistics: (patch: Partial<WizardLogisticsProfile>) => void;
  setLaboratory: (patch: Partial<WizardLaboratoryProfile>) => void;
  setLogo: (file: File | null) => void;
  adoptCompany: (companyId: number, locked: boolean) => void;
  /** Drop a persisted company id (stale verified row, 404, abandoned attempt). */
  clearCompany: () => void;
  /** Copy server-side requisites over the draft (after an E-IMZO signature). */
  hydrateFromCompany: (company: CompanyDetail) => void;
  reset: () => void;
}

const emptyIdentity: WizardIdentity = {
  jurisdiction: DEFAULT_JURISDICTION,
  tax_id: "",
  legal_name: "",
  short_name: "",
  legal_form: "",
  legal_address: "",
  actual_address: "",
  registration_number: "",
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

export const emptyManufacturer: WizardManufacturerProfile = {
  production_type: "",
  main_products: "",
  annual_capacity_tons: "",
  production_lines: "",
  employees: "",
  markets: ["domestic"],
  export_countries: [],
  founded_year: "",
  iso_certification: "",
  moq_tons: "",
  min_annual_volume_tons: "",
  financial_requirements: {
    bank_guarantee: true,
    letter_of_credit: true,
    payment_deferral: false,
    prepayment: true,
  },
  additional_requirements: [],
  additional_other: "",
};

export const emptyLogistics: WizardLogisticsProfile = {
  city: "",
  services: [],
  from_countries: [],
  to_countries: [],
  popular_routes: [],
  cargo_types: [],
  capabilities: [],
  tariff_model: "",
};

export const emptyLaboratory: WizardLaboratoryProfile = {
  city: "",
  website: "",
  email: "",
  phone: "",
  description: "",
};

/**
 * Registration is long enough that losing it to a stray reload is a real cost: the
 * store used to be plain in-memory state, so a refresh (or a crash, or a
 * back-navigation out of the flow) silently discarded every field the user had
 * typed and dropped them on the same step with a blank form.
 *
 * `documents` and `logo` are deliberately NOT persisted — a `File` has no
 * serialisable form, and a filename without its bytes would be a lie the user
 * only discovers at upload time. Losing them is safe: the wizard's reachability
 * guard sends the user back to re-attach.
 */
const PERSIST_KEY = "imex.company-wizard.draft";

export const useWizardDraft = create<WizardDraftState>()(
  persist(
    (set) => ({
      accountType: "",
      identity: { ...emptyIdentity },
      bank: { ...emptyBank },
      documents: {},
      manufacturer: {
        ...emptyManufacturer,
        financial_requirements: { ...emptyManufacturer.financial_requirements },
      },
      logistics: { ...emptyLogistics },
      laboratory: { ...emptyLaboratory },
      logo: null,
      companyId: null,
      identityLocked: false,
      setAccountType: (id) =>
        set((s) => ({
          accountType: id,
          // A company created under another account type must not ride into the
          // new branch — especially a verified showcase row left in localStorage.
          companyId: id === s.accountType ? s.companyId : null,
          identityLocked: id === s.accountType ? s.identityLocked : false,
        })),
      setIdentity: (patch) => set((s) => ({ identity: { ...s.identity, ...patch } })),
      setBank: (patch) => set((s) => ({ bank: { ...s.bank, ...patch } })),
      setDocument: (kind, file) => set((s) => ({ documents: { ...s.documents, [kind]: file } })),
      setManufacturer: (patch) =>
        set((s) => ({
          manufacturer: {
            ...s.manufacturer,
            ...patch,
            financial_requirements: patch.financial_requirements
              ? { ...s.manufacturer.financial_requirements, ...patch.financial_requirements }
              : s.manufacturer.financial_requirements,
          },
        })),
      setLogistics: (patch) => set((s) => ({ logistics: { ...s.logistics, ...patch } })),
      setLaboratory: (patch) => set((s) => ({ laboratory: { ...s.laboratory, ...patch } })),
      setLogo: (file) => set({ logo: file }),
      adoptCompany: (companyId, locked) => set({ companyId, identityLocked: locked }),
      clearCompany: () => set({ companyId: null, identityLocked: false }),
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
            short_name: company.short_name ?? s.identity.short_name,
            director_name: company.director_name ?? s.identity.director_name,
            legal_form: s.identity.legal_form || (company.legal_form ?? ""),
            legal_address: s.identity.legal_address || (company.legal_address ?? ""),
            actual_address: s.identity.actual_address || (company.actual_address ?? ""),
            registration_number:
              s.identity.registration_number || (company.registration_number ?? ""),
            registration_date: s.identity.registration_date || (company.registration_date ?? ""),
          },
          logistics: {
            ...s.logistics,
            city:
              s.logistics.city ||
              (typeof company.logistics_profile?.city === "string"
                ? company.logistics_profile.city
                : ""),
          },
          laboratory: {
            ...s.laboratory,
            city:
              s.laboratory.city ||
              (typeof company.laboratory_profile?.city === "string"
                ? company.laboratory_profile.city
                : ""),
            website:
              s.laboratory.website ||
              (typeof company.laboratory_profile?.website === "string"
                ? company.laboratory_profile.website
                : ""),
            email:
              s.laboratory.email ||
              (typeof company.laboratory_profile?.email === "string"
                ? company.laboratory_profile.email
                : ""),
            phone:
              s.laboratory.phone ||
              (typeof company.laboratory_profile?.phone === "string"
                ? company.laboratory_profile.phone
                : ""),
            description:
              s.laboratory.description ||
              (typeof company.laboratory_profile?.description === "string"
                ? company.laboratory_profile.description
                : ""),
          },
        })),
      reset: () =>
        set({
          accountType: "",
          identity: { ...emptyIdentity },
          bank: { ...emptyBank },
          documents: {},
          manufacturer: {
            ...emptyManufacturer,
            financial_requirements: { ...emptyManufacturer.financial_requirements },
          },
          logistics: { ...emptyLogistics },
          laboratory: { ...emptyLaboratory },
          logo: null,
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
        manufacturer: s.manufacturer,
        logistics: s.logistics,
        laboratory: s.laboratory,
        companyId: s.companyId,
        identityLocked: s.identityLocked,
      }),
    },
  ),
);
