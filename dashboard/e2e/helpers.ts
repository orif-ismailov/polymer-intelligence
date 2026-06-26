/**
 * Shared e2e constants/helpers.
 *
 * Seeded dev credentials come from backend/app/seed/data/staff_users.json
 * (password_dev_default — used when SEED_*_PASSWORD env vars are unset, i.e. dev/CI).
 * These are intentionally non-secret local-only defaults.
 *
 * i18n: the dashboard serves under /[locale]/ (next-intl) with `ru` as the default
 * locale, so the default UI text is Russian. Specs navigate with an explicit /ru
 * prefix via `p()` and assert against the `ru` message catalog (`M`) — the same
 * source of truth the UI renders from — so a wording change can't silently break a
 * spec, and the assertions stay correct in the default locale.
 */
import type { Page } from "@playwright/test";

import ru from "../messages/ru.json";

export const ADMIN = {
  email: "admin@polymer.uz",
  password: "admin_dev_password_change_in_prod",
} as const;

/** Default locale the dashboard redirects to. */
export const LOCALE = "ru";

/** Default-locale message catalog — assert page text against these keys. */
export const M = ru;

/** Prefix a dashboard path with the active locale (so there is no redirect hop). */
export function p(path: string): string {
  return path === "/" ? `/${LOCALE}` : `/${LOCALE}${path}`;
}

/** Drive the real login form and wait for the dashboard to load. */
export async function loginViaUi(page: Page, user = ADMIN): Promise<void> {
  await page.goto(p("/login"));
  await page.locator('input[type="email"]').fill(user.email);
  await page.locator('input[type="password"]').fill(user.password);
  await page.getByRole("button", { name: M.login.signIn }).click();
  // Lands on the dashboard root (not /login) once the access token is set.
  // The path is locale-prefixed (e.g. /ru/login), so match the "login" segment
  // anywhere rather than at the path root.
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15_000 });
}
