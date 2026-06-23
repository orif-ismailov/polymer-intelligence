/**
 * Shared e2e constants/helpers.
 *
 * Seeded dev credentials come from backend/app/seed/data/staff_users.json
 * (password_dev_default — used when SEED_*_PASSWORD env vars are unset, i.e. dev/CI).
 * These are intentionally non-secret local-only defaults.
 */
export const ADMIN = {
  email: "admin@polymer.uz",
  password: "admin_dev_password_change_in_prod",
} as const;

import type { Page } from "@playwright/test";

/** Drive the real login form and wait for the dashboard to load. */
export async function loginViaUi(page: Page, user = ADMIN): Promise<void> {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(user.email);
  await page.locator('input[type="password"]').fill(user.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  // Lands on the dashboard root (not /login) once the access token is set.
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
}
