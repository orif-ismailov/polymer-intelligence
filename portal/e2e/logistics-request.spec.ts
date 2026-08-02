import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * «Быстрая заявка на логистику» — carrier profile → one form → sent.
 *
 * The path this covers is the one the feature exists for: a carrier publishes no
 * offers, so before this the profile's action bar had nothing to point at
 * («Написать» switched to an empty products tab and was disabled by
 * `offer_count === 0` anyway). What is asserted is that the CTA now goes
 * somewhere, that the form is ONE screen rather than a wizard, and that a
 * submitted request comes back with its `LRQ-` number.
 *
 * Requires a live migrated+seeded API on :8000 exposing the dev-only
 * `GET /portal/auth/otp/peek`, and at least one verified logistics company.
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

async function login(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.goto("/cabinet/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();
  await page.waitForURL("**/cabinet/login/code");

  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  expect(res.ok()).toBeTruthy();
  const { code } = (await res.json()) as { code: string };

  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/cabinet/login"));
}

async function anyCarrierId(request: APIRequestContext): Promise<number | null> {
  const res = await request.get(`${API_BASE}/public/directories/logistics`, {
    params: { limit: 1 },
  });
  if (!res.ok()) return null;
  const body = (await res.json()) as { items?: { id: number }[] };
  return body.items?.[0]?.id ?? null;
}

test("a buyer sends a logistics request from the carrier's public profile", async ({
  page,
  request,
}) => {
  const carrierId = await anyCarrierId(request);
  test.skip(carrierId === null, "no verified logistics company in this environment");

  // A buyer needs its OWN company to act as — the request is company-to-company.
  await login(page, request, uniquePhone());
  await registerCompany(page, uniqueTaxId());

  await page.goto(`/logistics/${carrierId}`);
  await page.getByTestId("logistics-request-cta").click();
  await page.waitForURL(`**/cabinet/logistics/${carrierId}/request`);

  // One screen: everything the mockup draws is present at once, with no step
  // navigation between the cargo section and the route section.
  const form = page.getByTestId("logistics-request-form");
  await expect(form).toBeVisible();
  await expect(page.getByLabel(/cargo name|наименование груза|yuk nomi/i)).toBeVisible();
  await expect(page.getByLabel(/^(volume|объём|hajmi)/i)).toBeVisible();
  await expect(form.getByRole("combobox")).toHaveCount(3); // packaging + 2 countries

  await page.getByLabel(/cargo name|наименование груза|yuk nomi/i).fill("Полипропилен (PP)");
  await page.getByLabel(/^(volume|объём|hajmi)/i).fill("500");

  const selects = form.getByRole("combobox");
  await selects.nth(0).selectOption("containers");
  await selects.nth(1).selectOption("CN");
  await selects.nth(2).selectOption("UZ");

  const cities = page.getByLabel(/^(city|город|shahar)/i);
  await cities.nth(0).fill("Шанхай");
  await cities.nth(1).fill("Ташкент");

  await page.getByTestId("logistics-request-submit").click();

  await page.waitForURL(/\/cabinet\/logistics\/requests\/\d+\/done/, { timeout: 15_000 });
  const done = page.getByTestId("logistics-request-done");
  await expect(done).toBeVisible();
  await expect(done).toContainText(/LRQ-\d{4}-\d{6}/);
  // Country CODES must not reach the screen — `CN, Шанхай` is the storage format.
  await expect(done).not.toContainText(/\bCN\b/);
});

test("the form refuses to submit without cargo, volume and both countries", async ({
  page,
  request,
}) => {
  const carrierId = await anyCarrierId(request);
  test.skip(carrierId === null, "no verified logistics company in this environment");

  await login(page, request, uniquePhone());
  await registerCompany(page, uniqueTaxId());

  await page.goto(`/cabinet/logistics/${carrierId}/request`);
  await page.getByTestId("logistics-request-submit").click();

  // Still here — and saying why, rather than failing silently.
  await expect(page).toHaveURL(new RegExp(`/cabinet/logistics/${carrierId}/request$`));
  await expect(page.getByRole("alert").first()).toBeVisible();
});
