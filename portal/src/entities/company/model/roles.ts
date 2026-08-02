import type { CompanySummary } from "./types";

/**
 * Business roles, as the cabinet asks about them.
 *
 * These read the CONFIRMED roles on the acting company — a role a company merely
 * declared during registration is a tick-box, and gating a screen on it would let
 * anyone into it. `CompanySummaryOut.roles` already filters to confirmed.
 */
export function isCarrierCompany(company: CompanySummary | null | undefined): boolean {
  return company?.confirmed_roles?.includes("logistics_provider") ?? false;
}

export function isLaboratoryCompany(
  company: CompanySummary | null | undefined,
): boolean {
  return company?.confirmed_roles?.includes("laboratory") ?? false;
}
