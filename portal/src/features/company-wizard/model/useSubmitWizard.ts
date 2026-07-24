import { useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { companyApi, companyKeys, useActiveCompanyStore } from "@/entities/company";
import { verificationApi, verificationKeys } from "@/entities/verification";
import { ApiError } from "@/shared/api";

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
  /** Raw message from the server, if any. */
  detail?: string;
}

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

  function mapError(err: unknown): SubmitError {
    if (err instanceof ApiError) {
      if (err.status === 409) return { messageKey: "wizard.errors.duplicate" };
      return { messageKey: "wizard.errors.createFailed", detail: err.message };
    }
    return { messageKey: "wizard.errors.createFailed" };
  }

  async function submit(): Promise<number | null> {
    setError(null);
    const { identity, roles, bank, documents } = useWizardDraft.getState();

    try {
      setStage("creating");
      const created = await companyApi.create({
        jurisdiction: identity.jurisdiction,
        tax_id: identity.tax_id.trim(),
      });
      const companyId = created.id;

      setStage("profile");
      await companyApi.updateProfile(companyId, {
        legal_name: identity.legal_name.trim() || undefined,
        legal_form: identity.legal_form.trim() || undefined,
        legal_address: identity.legal_address.trim() || undefined,
        director_name: identity.director_name.trim() || undefined,
      });

      if (roles.length > 0) {
        setStage("roles");
        await companyApi.setRoles(companyId, roles);
      }

      if (bank.enabled) {
        setStage("bank");
        await companyApi.addBankAccount(companyId, {
          bank_mfo: bank.bank_mfo.trim(),
          account_number: bank.account_number.trim(),
          bank_name: bank.bank_name.trim() || undefined,
          currency: bank.currency || undefined,
        });
      }

      setStage("documents");
      for (const [kind, file] of Object.entries(documents)) {
        if (file instanceof File) {
          await companyApi.uploadDocument(companyId, kind, file);
        }
      }

      setStage("submitting");
      const caseOut = await verificationApi.submit(companyId);
      qc.setQueryData(verificationKeys.detail(companyId), caseOut);

      setStage("done");
      setActiveCompany(companyId);
      draft.reset();
      await qc.invalidateQueries({ queryKey: companyKeys.list() });
      await qc.invalidateQueries({ queryKey: companyKeys.detail(companyId) });
      return companyId;
    } catch (err) {
      setStage("idle");
      setError(mapError(err));
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
