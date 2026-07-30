import { useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { companyApi, companyKeys, useActiveCompanyStore } from "@/entities/company";
import type { CompanyProfilePatch } from "@/entities/company";
import { verificationApi, verificationKeys } from "@/entities/verification";
import type { CaseOut } from "@/entities/verification";
import { ApiError } from "@/shared/api";
import { MAX_UPLOAD_MB } from "@/shared/config";

import { ACCOUNT_TYPES } from "./constants";
import { useWizardDraft } from "./draftStore";

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
    const { identity, accountType, bank, documents, identityLocked } = draft;
    const taxId = identity.tax_id.trim();
    // Tracked locally: `stage` state is stale inside this closure's catch.
    let failedAt: SubmitStage = "creating";
    function advance(next: SubmitStage): void {
      failedAt = next;
      setStage(next);
    }

    try {
      // Three ways in: signed on step 1 (draft.companyId), a previous attempt that
      // got past `create` and failed later (createdRef), or a fresh registration.
      // Re-creating would 409 on the unique tax_id and strand the user.
      const resumable = createdRef.current;
      const companyId =
        draft.companyId ??
        (resumable?.taxId === taxId
          ? resumable.id
          : await (async () => {
              advance("creating");
              const created = await companyApi.create({
                jurisdiction: identity.jurisdiction,
                tax_id: taxId,
              });
              createdRef.current = { id: created.id, taxId };
              // Record it on the DRAFT too, not just this hook's ref. `createdRef`
              // belongs to StepReview, so pressing «Назад» to fix a rejected
              // document unmounted it and lost the id — the retry then re-ran
              // `create`, hit 409 on its own tax_id, and the wizard could never be
              // completed for that STIR. The draft outlives the step.
              adoptCompany(created.id, false);
              return created.id;
            })());

      advance("profile");
      const patch: CompanyProfilePatch = {
        legal_form: identity.legal_form.trim() || undefined,
        legal_address: identity.legal_address.trim() || undefined,
        registration_date: identity.registration_date || undefined,
      };
      if (!identityLocked) {
        patch.legal_name = identity.legal_name.trim() || undefined;
        patch.director_name = identity.director_name.trim() || undefined;
      }
      await companyApi.updateProfile(companyId, patch);

      const role = ACCOUNT_TYPES.find((spec) => spec.id === accountType)?.role;
      if (role) {
        advance("roles");
        await companyApi.setRoles(companyId, [role]);
      }

      if (bank.enabled) {
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
