import { expect, test } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * Happy-path e2e: OTP login → company wizard → verification submit → offer create.
 *
 * Requires a live migrated+seeded API on :8000 exposing the dev-only
 * the seeded demo logins endpoint. It is a valid harness but is not run in
 * CI here (no live backend).
 */

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

test("an account with no company is sent to registration", async ({ page }) => {
  await login(page, await provisionAccount(request));

  // The cabinet is company-scoped end to end, so the gate redirects rather than
  // rendering a shell of empty states the user cannot resolve.
  await page.waitForURL("**/cabinet/onboarding");
  await expect(page.getByTestId("onboarding-start")).toBeVisible();

  await page.getByTestId("onboarding-start").click();
  await page.waitForURL("**/cabinet/companies/new/1");
});

test("register a company and publish an offer", async ({ page }) => {
  const taxId = uniqueTaxId();

  await login(page, await provisionAccount(request));
  await registerCompany(page, taxId);

  // The success sheet leads into the cabinet.
  await page.getByTestId("wizard-done-cabinet").click();
  await page.waitForURL((url) => url.pathname === "/cabinet");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
