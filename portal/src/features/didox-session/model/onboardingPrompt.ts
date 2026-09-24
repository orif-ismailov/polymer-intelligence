/**
 * «Show the Didox onboarding once per visit».
 *
 * The owner of a verified company not yet on Didox is taken to `/cabinet/didox`
 * on entering the cabinet — once. «Позже» (or simply leaving the screen) lets
 * them work; the next visit asks again, until the company is ready. Kept in
 * `sessionStorage`, so a reload does not nag but a new sign-in does.
 */
const key = (companyId: number) => `didox-onboarding-prompted:${companyId}`;

export function wasPrompted(companyId: number): boolean {
  try {
    return sessionStorage.getItem(key(companyId)) === "1";
  } catch {
    // Storage blocked: prompting every time is safer than never.
    return false;
  }
}

export function markPrompted(companyId: number): void {
  try {
    sessionStorage.setItem(key(companyId), "1");
  } catch {
    /* nothing to remember it in — the redirect still happens once per mount */
  }
}
