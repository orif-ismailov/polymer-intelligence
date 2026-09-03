import { useEffect } from "react";

import { useCompanyLookup, isLookupableTaxId } from "@/entities/company";
import { ApiError } from "@/shared/api";

import { useWizardDraft } from "./draftStore";

export type RegistryPrefillStatus =
  | "idle"
  | "loading"
  | "filled"
  | "not_found"
  | "unavailable";

export interface RegistryPrefill {
  status: RegistryPrefillStatus;
  /** Registry-filled field names, for the "where did this come from" hint. */
  prefilled: string[];
  /** The registry's own wording for the company's state, when it gave one. */
  registryStatusText: string | null;
}

/**
 * Fill the wizard from the state registry once the STIR is known.
 *
 * The STIR arrives one of two ways — read out of the E-IMZO certificate at step
 * 1, or typed at step 2 — and either way this asks Didox for the tax registry's
 * record and drops it into the blanks (`hydrateFromRegistry` never overwrites).
 *
 * Every failure is soft on purpose. A registration is a person filling in
 * fields they already know; a provider we chose to integrate must never be able
 * to stop that. So "no such company", "no channel configured" and "the provider
 * is down" all resolve to a status the UI mentions in one line, and the form
 * stays exactly as typeable as it was before.
 */
export function useRegistryPrefill(): RegistryPrefill {
  const taxId = useWizardDraft((s) => s.identity.tax_id);
  const companyId = useWizardDraft((s) => s.companyId);
  const prefilled = useWizardDraft((s) => s.prefilled);
  const hydrateFromRegistry = useWizardDraft((s) => s.hydrateFromRegistry);

  const query = useCompanyLookup(taxId, companyId);
  const company = query.data?.found ? (query.data.company ?? null) : null;

  useEffect(() => {
    if (company) hydrateFromRegistry(company);
  }, [company, hydrateFromRegistry]);

  if (!isLookupableTaxId(taxId)) {
    return { status: "idle", prefilled, registryStatusText: null };
  }
  if (query.isLoading) {
    return { status: "loading", prefilled, registryStatusText: null };
  }
  if (query.isError) {
    // A deployment with no registry channel is the shipped default and says
    // nothing on screen — announcing a feature the applicant has never seen is
    // noise. A configured channel that failed is worth one line.
    const notConfigured =
      query.error instanceof ApiError && query.error.code === "registry_not_configured";
    return {
      status: notConfigured ? "idle" : "unavailable",
      prefilled,
      registryStatusText: null,
    };
  }
  if (query.data && !query.data.found) {
    return { status: "not_found", prefilled, registryStatusText: null };
  }
  if (company) {
    return {
      status: "filled",
      prefilled,
      registryStatusText: company.registry_status_text ?? null,
    };
  }
  return { status: "idle", prefilled, registryStatusText: null };
}
