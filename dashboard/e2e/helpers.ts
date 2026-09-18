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
import { test as base, type BrowserContext, type Page } from "@playwright/test";

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

/**
 * Sign this browser context in, by calling the real login endpoint.
 *
 * Goes through the dev server rather than straight at the backend on purpose: the
 * dashboard calls the RELATIVE `/api/v1`, so the refresh cookie has to belong to
 * the Next origin. A cookie set on `localhost:8000` is never sent from a page on
 * `localhost:3137`, and the symptom would be an unexplained login screen.
 */
export async function loginViaApi(context: BrowserContext, user = ADMIN): Promise<void> {
  const res = await context.request.post("/api/v1/auth/login", {
    data: { email: user.email, password: user.password },
  });
  if (!res.ok()) {
    throw new Error(`e2e login failed: ${res.status()} ${await res.text()}`);
  }
}

/**
 * The authenticated `test` for dashboard specs: one fresh session per test.
 *
 * **Why this replaced a saved `storageState`.** That file is a SNAPSHOT of a
 * refresh cookie, replayed into every test's context. Since IMEX-1 the refresh
 * token rotates and its predecessor is invalidated, so the first test spent the
 * saved cookie and every later context presented a token that had already been
 * used — which is exactly what a stolen cookie looks like, and is treated as one:
 * the family is revoked and everything afterwards answers 401. The whole suite
 * landed on the login screen.
 *
 * Nothing is wrong with the application here; the harness was relying on the one
 * behaviour rotation exists to forbid. A login per test costs one argon2 hash and
 * gives each test its own family, which is also a truer simulation of a person.
 */
export const test = base.extend({
  context: async ({ context }, use) => {
    await loginViaApi(context);
    await use(context);
  },
});

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
