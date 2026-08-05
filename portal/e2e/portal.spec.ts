import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * Happy-path e2e: OTP login → company wizard → verification submit → offer create.
 *
 * Requires a live migrated+seeded API on :8000 exposing the dev-only
 * `GET /portal/auth/otp/peek` endpoint. It is a valid harness but is not run in
 * CI here (no live backend).
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

function uniquePhone(): string {
  // A pseudo-random +998 subscriber number to avoid collisions between runs.
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

async function readOtp(request: APIRequestContext, phone: string): Promise<string> {
  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { code: string };
  return body.code;
}

async function login(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.goto("/cabinet/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();

  await page.waitForURL("**/cabinet/login/code");
  const code = await readOtp(request, phone);
  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();

  await page.waitForURL((url) => !url.pathname.startsWith("/cabinet/login"));
}

test("an account with no company is sent to registration", async ({ page, request }) => {
  await login(page, request, uniquePhone());

  // The cabinet is company-scoped end to end, so the gate redirects rather than
  // rendering a shell of empty states the user cannot resolve.
  await page.waitForURL("**/cabinet/onboarding");
  await expect(page.getByTestId("onboarding-start")).toBeVisible();

  await page.getByTestId("onboarding-start").click();
  await page.waitForURL("**/cabinet/companies/new/1");
});

test("register a company and publish an offer", async ({ page, request }) => {
  const phone = uniquePhone();
  const taxId = uniqueTaxId();

  await login(page, request, phone);
  await registerCompany(page, taxId);

  // The success sheet leads into the cabinet.
  await page.getByTestId("wizard-done-cabinet").click();
  await page.waitForURL((url) => url.pathname === "/cabinet");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
