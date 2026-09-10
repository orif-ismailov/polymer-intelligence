import { ApiError } from "@/shared/api";

/**
 * The API's typed refusals, in the words of the person reading them.
 *
 * Without this the alert printed the code itself — a supplier who opened an
 * all-suppliers tender was told «company_not_verified» and had to guess, and
 * the buyer's accept was showing «request_closed» the same way. Keyed by `code`
 * OR `message`: FastAPI's `detail` is a bare string on most of these refusals,
 * and the client only fills `code` when it is an object.
 *
 * Two maps rather than one, because the two sides of a tender read the SAME
 * code differently. `request_closed` means "you cannot quote on this" to a
 * supplier and "you cannot pick a winner for this" to the buyer who just
 * cancelled it; one string cannot be true for both without going vague.
 */
const SHARED: Record<string, string> = {
  company_not_verified: "rfq.errors.notVerified",
};

/** A supplier submitting a quote (`POST …/responses`). */
export const SUBMIT_ERRORS: Record<string, string> = {
  ...SHARED,
  role_not_allowed: "rfq.errors.roleNotAllowed",
  already_responded: "rfq.errors.alreadyResponded",
  request_closed: "rfq.errors.requestClosed",
  own_request: "rfq.errors.ownRequest",
  unknown_incoterms: "rfq.errors.unknownIncoterms",
};

/** The buyer choosing a winner (`POST …/responses/{id}/accept`). */
export const ACCEPT_ERRORS: Record<string, string> = {
  ...SHARED,
  request_closed: "rfq.errors.acceptRequestClosed",
  response_closed: "rfq.errors.acceptResponseClosed",
  already_accepted: "rfq.errors.acceptAlreadyAccepted",
};

/**
 * Resolve an error to a translated sentence, falling back to the generic one.
 *
 * `fallback404` exists because a 404 on the submit path means the tender has
 * stopped being visible to this supplier, which is the closed case wearing a
 * different status code.
 */
export function rfqErrorMessage(
  err: unknown,
  t: (key: string) => string,
  map: Record<string, string>,
  fallback404?: string,
): string {
  if (err instanceof ApiError) {
    const key = map[err.code ?? ""] ?? map[err.message];
    if (key) return t(key);
    if (err.status === 404 && fallback404) return t(fallback404);
  }
  return t("errors.generic");
}
