import { useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { companyApi, companyKeys, useActiveCompanyStore } from "@/entities/company";
import { verificationApi, verificationKeys } from "@/entities/verification";
import { ApiError } from "@/shared/api";
import { MAX_UPLOAD_MB } from "@/shared/config";

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
 * Server-side upload rejections (`storage_service.validate_upload`) mapped to
 * translated messages — the raw code must never reach the user.
 */
const UPLOAD_DETAIL_KEYS: Record<string, string> = {
  file_too_large: "wizard.documents.tooLarge",
  invalid_file_type: "wizard.documents.invalidType",
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

interface SubmitResult {
  submit: () => Promise<number | null>;
  stage: SubmitStage;
  error: SubmitError | null;
  isSubmitting: boolean;
  reset: () => void;
}

/**
 * Orchestrates the full "confirm" flow as an ordered sequence of API calls:
 *   create → patch profile → set roles → add bank → upload docs → submit case.
 * Any failure short-circuits with a typed, translatable error. On success it
 * resets the draft, sets the new company active, and returns its id.
 */
export function useSubmitWizard(): SubmitResult {
  const qc = useQueryClient();
  const draft = useWizardDraft();
  const setActiveCompany = useActiveCompanyStore((s) => s.setActiveCompany);
  const [stage, setStage] = useState<SubmitStage>("idle");
  const [error, setError] = useState<SubmitError | null>(null);
  /** Company created by an attempt that failed later — reused so a retry resumes. */
  const createdRef = useRef<{ id: number; taxId: string } | null>(null);

  function mapError(err: unknown, failedAt: SubmitStage): SubmitError {
    if (err instanceof ApiError) {
      if (err.status === 409) return { messageKey: "wizard.errors.duplicate" };
      const uploadKey = UPLOAD_DETAIL_KEYS[err.message];
      if (uploadKey) {
        return { messageKey: uploadKey, messageValues: { mb: MAX_UPLOAD_MB } };
      }
      return {
        messageKey: STAGE_MESSAGE_KEYS[failedAt] ?? "wizard.errors.createFailed",
        detail: err.message,
      };
    }
    return { messageKey: STAGE_MESSAGE_KEYS[failedAt] ?? "wizard.errors.createFailed" };
  }

  async function submit(): Promise<number | null> {
    setError(null);
    const { identity, roles, bank, documents } = useWizardDraft.getState();
    const taxId = identity.tax_id.trim();
    // Tracked locally: `stage` state is stale inside this closure's catch.
    let failedAt: SubmitStage = "creating";
    function advance(next: SubmitStage): void {
      failedAt = next;
      setStage(next);
    }

    try {
      // A previous attempt may have created the company and then failed further
      // down (a rejected document, say). Re-creating it would 409 on the unique
      // tax_id and strand the user, so resume from the company we already made —
      // but only while the identity step still refers to it.
      const resumable = createdRef.current;
      const companyId =
        resumable?.taxId === taxId
          ? resumable.id
          : await (async () => {
              advance("creating");
              const created = await companyApi.create({
                jurisdiction: identity.jurisdiction,
                tax_id: taxId,
              });
              createdRef.current = { id: created.id, taxId };
              return created.id;
            })();

      advance("profile");
      await companyApi.updateProfile(companyId, {
        legal_name: identity.legal_name.trim() || undefined,
        legal_form: identity.legal_form.trim() || undefined,
        legal_address: identity.legal_address.trim() || undefined,
        director_name: identity.director_name.trim() || undefined,
      });

      if (roles.length > 0) {
        advance("roles");
        await companyApi.setRoles(companyId, roles);
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
      const caseOut = await verificationApi.submit(companyId);
      qc.setQueryData(verificationKeys.detail(companyId), caseOut);

      createdRef.current = null;
      setStage("done");
      setActiveCompany(companyId);
      draft.reset();
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
