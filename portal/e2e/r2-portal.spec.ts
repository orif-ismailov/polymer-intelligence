import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * R2 demo e2e: OTP login → register a company → create a purchase request through
 * the 4-step wizard → see it in the requests list with a status timeline → browse
 * the market, news and notification surfaces.
 *
 * Buying never requires a verified company, so this whole flow is self-serve (no
 * staff moderation). Requires a live migrated+seeded API on :8000 exposing the
 * dev-only `GET /portal/auth/otp/peek`. Not run in CI here (no live backend).
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

function uniquePhone(): string {
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
  await page.goto("/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();
  await page.waitForURL("**/login/code");
  const code = await readOtp(request, phone);
  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}


test("buyer creates a purchase request and browses the R2 surfaces", async ({ page, request }) => {
  const phone = uniquePhone();
  await login(page, request, phone);
  await registerCompany(page, uniqueTaxId());

  // ── Purchase request through the 5-step wizard ──────────────────────────────
  await page.goto("/requests");
  // Two identical CTAs render on /requests (header + empty state) — take the header one.
  await page.getByRole("link", { name: /new request|новая заявка|yangi ariza/i }).first().click();
  await page.waitForURL("**/requests/new/**");

  // Step 1 — pick manual product entry
  await page.getByTestId("request-wizard-manual").click();
  await page.getByTestId("request-wizard-product-text").fill("HDPE film grade");
  await page.getByTestId("request-wizard-grade").fill("F0348");
  await page.getByTestId("request-wizard-next").click();

  // Step 2 — volume (defaults for the rest)
  await page.getByTestId("request-wizard-volume").fill("50");
  await page.getByTestId("request-wizard-next").click();

  // Step 3 — extra (optional)
  await page.getByTestId("request-wizard-next").click();

  // Step 4 — communication (defaults)
  await page.getByTestId("request-wizard-next").click();

  // Step 5 — publish
  await page.getByTestId("request-wizard-publish").click();

  // Lands on the published celebration, then the list still has the request.
  await page.waitForURL(/\/requests\/new\/done\/\d+$/);
  await expect(page.getByTestId("request-wizard-done")).toBeVisible();
  await page.getByTestId("request-wizard-done-list").click();
  await page.waitForURL("**/requests");
  await expect(page.getByText(/REQ-|IMX-/).first()).toBeVisible();

  // ── Browse the other R2 surfaces (may be empty — headings must render) ──────
  await page.goto("/market");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  await page.goto("/news");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  await page.goto("/notifications");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
