import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

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
  await page.goto("/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();

  await page.waitForURL("**/login/code");
  const code = await readOtp(request, phone);
  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();

  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

test("register a company and publish an offer", async ({ page, request }) => {
  const phone = uniquePhone();
  const taxId = uniqueTaxId();

  await login(page, request, phone);

  // Step 1 — identity.
  await page.goto("/companies/new/1");
  await page.getByLabel(/tax id|инн|stir/i).fill(taxId);
  await page.getByRole("button", { name: /next|далее|keyingisi/i }).click();

  // Step 2 — roles.
  await page.waitForURL("**/companies/new/2");
  await page.getByText(/trader|трейдер|treyder/i).first().click();
  await page.getByRole("button", { name: /next|далее|keyingisi/i }).click();

  // Step 3 — bank (skip).
  await page.waitForURL("**/companies/new/3");
  await page.getByRole("button", { name: /skip|пропустить|o.tkazib/i }).click();

  // Step 4 — documents (a required registration certificate).
  await page.waitForURL("**/companies/new/4");
  await page.setInputFiles('input[type="file"]', {
    name: "registration.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test document"),
  });
  await page.getByRole("button", { name: /next|далее|keyingisi/i }).click();

  // Step 5 — confirm + submit.
  await page.waitForURL("**/companies/new/5");
  await page.getByRole("button", { name: /submit|создать|yaratish/i }).click();

  // Lands on the verification status screen.
  await page.waitForURL(/\/companies\/\d+\/verification/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
