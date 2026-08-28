import {
  isCarrierCompany,
  isLaboratoryCompany,
  type CompanySummary,
} from "@/entities/company";

/**
 * The i18n key for the `/cabinet/requests` slot, which is three pages behind one
 * address (`app/router/RequestsRouteSwitch.tsx`).
 *
 * A buyer files tenders there; a carrier and a laboratory read their broadcast
 * pool. Renaming the entry «Тендеры» unconditionally would put that word over a
 * carrier's logistics pool, so the label follows the same rule the switch does.
 */
export function requestsNavLabelKey(
  company: CompanySummary | null | undefined,
): "nav.requests" | "nav.tenders" {
  if (isCarrierCompany(company) || isLaboratoryCompany(company)) return "nav.requests";
  return "nav.tenders";
}

/** One-line description of that same slot, for the home page's module card. */
export function requestsNavHintKey(
  company: CompanySummary | null | undefined,
): "logisticsRequest.poolSubtitle" | "labRequest.poolSubtitle" | "requests.subtitle" {
  if (isCarrierCompany(company)) return "logisticsRequest.poolSubtitle";
  if (isLaboratoryCompany(company)) return "labRequest.poolSubtitle";
  return "requests.subtitle";
}
