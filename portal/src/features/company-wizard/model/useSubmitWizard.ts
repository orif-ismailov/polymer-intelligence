import { useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { companyApi, companyKeys, useActiveCompanyStore } from "@/entities/company";
import type {
  CompanyProfilePatch,
  LaboratoryProfile,
  LogisticsProfile,
  ManufacturerProfile,
} from "@/entities/company";
import { verificationApi, verificationKeys } from "@/entities/verification";
import type { CaseOut } from "@/entities/verification";
import { ApiError } from "@/shared/api";
import { MAX_UPLOAD_MB } from "@/shared/config";

import {
  ACCOUNT_TYPES,
  isLaboratoryType,
  isLogisticsType,
  isManufacturerType,
} from "./constants";
import { useWizardDraft } from "./draftStore";
import type {
  WizardLaboratoryProfile,
  WizardLogisticsProfile,
  WizardManufacturerProfile,
} from "./draftStore";

export type SubmitStage =
  | "idle"
  | "creating"
  | "profile"
  | "roles"
  | "bank"
  | "documents"
  | "submitting"
  | "done";

export interface SubmitError {
  /** i18n key for the message to show. */
  messageKey: string;
  /** Interpolation values for `messageKey`, if any. */
  messageValues?: Record<string, string | number>;
  /** Raw message from the server, if any. */
  detail?: string;
}

/**
 * Server-side rejections mapped to translated messages — a raw server string must
 * never reach the user. Anything not listed here falls back to a per-stage message
 * (see STAGE_MESSAGE_KEYS) rather than being printed verbatim: the API answers in
 * English ("UZ STIR must be exactly 9 digits", "Daily limit reached") and this UI
 * is Russian first.
 */
const SERVER_DETAIL_KEYS: Record<string, string> = {
  // storage_service.validate_upload
  file_too_large: "wizard.documents.tooLarge",
  invalid_file_type: "wizard.documents.invalidType",
  // company_service / portal.companies — every one of these is a 409, and they are
  // NOT all "this company already exists"; see mapError.
  "Company already registered": "wizard.errors.duplicate",
  "Profile not editable now": "wizard.errors.profileLocked",
  identity_locked: "wizard.errors.identityLocked",
  "No open case": "wizard.errors.noOpenCase",
  insufficient_company_role: "wizard.errors.insufficientRole",
  // company_service.normalize_new_company
  "UZ STIR must be exactly 9 digits": "wizard.details.taxIdInvalid",
  "jurisdiction must be a 2-letter country code": "wizard.errors.jurisdictionInvalid",
};

/**
 * Which step actually failed. Reporting "failed to create the company" after the
 * company was already created (e.g. a document was rejected) misdirects the user
 * to the one thing that DID work.
 */
const STAGE_MESSAGE_KEYS: Partial<Record<SubmitStage, string>> = {
  documents: "wizard.errors.documentFailed",
  submitting: "wizard.errors.submitFailed",
};

/**
 * Submit the case, tolerating one that is already in flight.
 *
 * `verification_service.submit_case` only accepts a case in `draft`/`needs_info`;
 * anything else is a 409 «Case not submittable». An E-IMZO signature on step 1 *is*
 * the first submit, so by the time the wizard reaches step 5 a signed company's
 * case is already `checks_running`/`pending_review` — and the wizard treated that
 * conflict as a failure, stranding the very flow the platform recommends.
 *
 * Re-submitting is not merely unnecessary, it would be destructive: `submit_case`
 * deletes and re-spawns every check, which would throw away the `eimzo_signature`
 * check and its evidence. So an already-submitted case is the success case — read it
 * back and carry on.
 */
async function submitOrAdoptExistingCase(companyId: number): Promise<CaseOut> {
  try {
    return await verificationApi.submit(companyId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 409 && err.message === "Case not submittable") {
      return await verificationApi.get(companyId);
    }
    throw err;
  }
}

interface SubmitResult {
  submit: () => Promise<number | null>;
  stage: SubmitStage;
  error: SubmitError | null;
  isSubmitting: boolean;
  reset: () => void;
}

/**
 * Orchestrates the whole registration as an ordered sequence of API calls:
 *   create → patch profile → set role → add bank → upload docs → submit case.
 * Any failure short-circuits with a typed, translatable error. On success it
 * sets the new company active and returns its id.
 *
 * The company may already exist when this runs: step 1's E-IMZO signature creates
 * it from the certificate's STIR. That id is carried on the draft, so the review
 * step patches the signed row rather than colliding with its unique tax_id.
 */
export function useSubmitWizard(): SubmitResult {
  const qc = useQueryClient();
  const setActiveCompany = useActiveCompanyStore((s) => s.setActiveCompany);
  const [stage, setStage] = useState<SubmitStage>("idle");
  const [error, setError] = useState<SubmitError | null>(null);
  /** Company created by an attempt that failed later — reused so a retry resumes. */
  const createdRef = useRef<{ id: number; taxId: string } | null>(null);
  /** Same id, recorded on the draft so it survives this component unmounting. */
  const adoptCompany = useWizardDraft((s) => s.adoptCompany);
  const clearCompany = useWizardDraft((s) => s.clearCompany);

  function mapError(err: unknown, failedAt: SubmitStage): SubmitError {
    if (err instanceof ApiError) {
      // Map on the server's detail code, never on the status alone. These endpoints
      // return 409 for at least four different reasons, and blanket-reporting every
      // one as «Компания с таким ИНН уже существует» told users their company was a
      // duplicate when the truth was that the profile was frozen.
      const known = SERVER_DETAIL_KEYS[err.message];
      if (known) {
        return { messageKey: known, messageValues: { mb: MAX_UPLOAD_MB } };
      }
      if (err.status === 429) {
        return { messageKey: "wizard.errors.rateLimited" };
      }
      if (err.status === 409) {
        // An unrecognised conflict: say it is a conflict, don't invent a cause.
        return { messageKey: "wizard.errors.conflict", detail: err.message };
      }
      return {
        messageKey: STAGE_MESSAGE_KEYS[failedAt] ?? "wizard.errors.createFailed",
        // `detail` is a server string in English — only shown as a secondary line
        // under a translated title, and only when we have nothing better.
        detail: err.message,
      };
    }
    return { messageKey: STAGE_MESSAGE_KEYS[failedAt] ?? "wizard.errors.createFailed" };
  }

  async function submit(): Promise<number | null> {
    setError(null);
    const draft = useWizardDraft.getState();
    const { identity, accountType, bank, documents, logo, manufacturer, logistics, laboratory } =
      draft;
    let { identityLocked } = draft;
    const taxId = identity.tax_id.trim();
    // Tracked locally: `stage` state is stale inside this closure's catch.
    let failedAt: SubmitStage = "creating";
    function advance(next: SubmitStage): void {
      failedAt = next;
      setStage(next);
    }

    try {
      // Persisted drafts can still point at a company that finished verification
      // (or was a showcase row). Patching those 409s — drop the id and create
      // fresh when the tax id is free.
      let resumeId = draft.companyId;
      if (resumeId != null) {
        try {
          const existing = await companyApi.get(resumeId);
          const editable =
            existing.status === "draft" || existing.status === "pending_verification";
          if (!editable) {
            clearCompany();
            createdRef.current = null;
            resumeId = null;
            identityLocked = false;
          } else {
            identityLocked = existing.identity_locked;
            adoptCompany(existing.id, existing.identity_locked);
          }
        } catch (err) {
          if (err instanceof ApiError && err.status === 404) {
            clearCompany();
            createdRef.current = null;
            resumeId = null;
            identityLocked = false;
          } else {
            throw err;
          }
        }
      }

      // Three ways in: signed on step 1 (draft.companyId), a previous attempt that
      // got past `create` and failed later (createdRef), or a fresh registration.
      // Re-creating would 409 on the unique tax_id and strand the user.
      const resumable = createdRef.current;
      const companyId =
        resumeId ??
        (resumable?.taxId === taxId
          ? resumable.id
          : await (async () => {
              advance("creating");
              const created = await companyApi.create({
                jurisdiction: identity.jurisdiction,
                tax_id: taxId,
              });
              createdRef.current = { id: created.id, taxId };
              adoptCompany(created.id, false);
              return created.id;
            })());

      advance("profile");
      const patch: CompanyProfilePatch = {
        legal_form: identity.legal_form.trim() || undefined,
        legal_address: identity.legal_address.trim() || undefined,
        actual_address: identity.actual_address.trim() || undefined,
        registration_number: identity.registration_number.trim() || undefined,
        short_name: identity.short_name.trim() || undefined,
        registration_date: identity.registration_date || undefined,
      };
      if (!identityLocked) {
        patch.legal_name = identity.legal_name.trim() || undefined;
        patch.director_name = identity.director_name.trim() || undefined;
      }
      if (isManufacturerType(accountType)) {
        patch.manufacturer_profile = toManufacturerProfilePayload(manufacturer);
      }
      if (isLogisticsType(accountType)) {
        patch.logistics_profile = toLogisticsProfilePayload(logistics);
      }
      if (isLaboratoryType(accountType)) {
        patch.laboratory_profile = toLaboratoryProfilePayload(laboratory);
      }
      await companyApi.updateProfile(companyId, patch);

      const roles = ACCOUNT_TYPES.find((spec) => spec.id === accountType)?.roles;
      if (roles && roles.length > 0) {
        advance("roles");
        await companyApi.setRoles(companyId, [...roles]);
      }

      if (
        bank.enabled &&
        !isManufacturerType(accountType) &&
        !isLogisticsType(accountType) &&
        !isLaboratoryType(accountType)
      ) {
        advance("bank");
        await companyApi.addBankAccount(companyId, {
          bank_mfo: bank.bank_mfo.trim(),
          account_number: bank.account_number.trim(),
          bank_name: bank.bank_name.trim() || undefined,
          currency: bank.currency || undefined,
        });
      }

      advance("documents");
      for (const [kind, file] of Object.entries(documents)) {
        if (file instanceof File) {
          await companyApi.uploadDocument(companyId, kind, file);
        }
      }
      if (logo instanceof File) {
        await companyApi.uploadLogo(companyId, logo);
      }

      advance("submitting");
      const caseOut = await submitOrAdoptExistingCase(companyId);
      qc.setQueryData(verificationKeys.detail(companyId), caseOut);

      createdRef.current = null;
      setStage("done");
      setActiveCompany(companyId);
      await qc.invalidateQueries({ queryKey: companyKeys.list() });
      await qc.invalidateQueries({ queryKey: companyKeys.detail(companyId) });
      return companyId;
    } catch (err) {
      setStage("idle");
      setError(mapError(err, failedAt));
      return null;
    }
  }


  return {
    submit,
    stage,
    error,
    isSubmitting: stage !== "idle" && stage !== "done",
    reset: () => {
      setStage("idle");
      setError(null);
    },
  };
}

function optionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : undefined;
}

function optionalInt(value: string): number | undefined {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return undefined;
  return Number(trimmed);
}

function toManufacturerProfilePayload(profile: WizardManufacturerProfile): ManufacturerProfile {
  return {
    production_type: profile.production_type.trim() || undefined,
    main_products: profile.main_products.trim() || undefined,
    annual_capacity_tons: optionalNumber(profile.annual_capacity_tons),
    production_lines: optionalInt(profile.production_lines),
    employees: optionalInt(profile.employees),
    markets: [...profile.markets],
    export_countries: [...profile.export_countries],
    founded_year: optionalInt(profile.founded_year),
    iso_certification: profile.iso_certification.trim() || undefined,
    moq_tons: optionalNumber(profile.moq_tons),
    min_annual_volume_tons: optionalNumber(profile.min_annual_volume_tons),
    financial_requirements: { ...profile.financial_requirements },
    additional_requirements: [...profile.additional_requirements],
    additional_other: profile.additional_other.trim() || undefined,
  };
}

function toLogisticsProfilePayload(profile: WizardLogisticsProfile): LogisticsProfile {
  return {
    city: profile.city.trim() || undefined,
    services: [...profile.services],
    from_countries: [...profile.from_countries],
    to_countries: [...profile.to_countries],
    popular_routes: [...profile.popular_routes],
    cargo_types: [...profile.cargo_types],
    capabilities: [...profile.capabilities],
    tariff_model: profile.tariff_model.trim() || undefined,
  };
}

function toLaboratoryProfilePayload(profile: WizardLaboratoryProfile): LaboratoryProfile {
  return {
    city: profile.city.trim() || undefined,
    website: profile.website.trim() || undefined,
    email: profile.email.trim() || undefined,
    phone: profile.phone.trim() || undefined,
    description: profile.description.trim() || undefined,
  };
}
