import { effectiveRoles } from "./features";
import type { CompanySummary } from "./types";

/**
 * Business roles, as the cabinet asks about them.
 *
 * These read the DECLARED (non-revoked) roles on the acting company — the
 * account type it registered as. The cabinet's shape follows registration
 * immediately; what stays behind CONFIRMED is the sensitive server side
 * (pool visibility, directories), which the backend gates on its own.
 */
export function isCarrierCompany(company: CompanySummary | null | undefined): boolean {
  return effectiveRoles(company).includes("logistics_provider");
}

export function isLaboratoryCompany(
  company: CompanySummary | null | undefined,
): boolean {
  return effectiveRoles(company).includes("laboratory");
}
