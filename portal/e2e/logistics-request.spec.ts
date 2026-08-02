import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * «Быстрая заявка на логистику» — broadcast, then a private conversation.
 *
 * A buyer states a job once and every verified carrier sees it at
 * `/cabinet/requests`, which is the page that is otherwise permanently empty for
 * a company that files no purchase requests of its own. The buyer's Заявки is
 * untouched, and this asserts that too — the role branch is the part most likely
 * to be broken by a later edit, and it fails silently (a carrier just sees an
 * empty list) rather than loudly.
 *
 * Requires a live migrated+seeded API on :8000 with the dev-only
 * `GET /portal/auth/otp/peek`, and at least one verified logistics company.
 *
 * Unlike the other specs, this one signs in as a SPECIFIC seeded account:
 * a carrier has to be a member of a company whose logistics role staff have
 * confirmed, which a freshly-registered throwaway company is not. That means the
 * same phone on every run, so the API needs `OTP_RESEND_COOLDOWN_SECONDS=0` or a
 * rerun inside a minute fails in `login` with a timeout that looks nothing like
 * its cause. Override the account with `PORTAL_CARRIER_PHONE`.
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";
const CARRIER_PHONE = process.env.PORTAL_CARRIER_PHONE ?? "+998901234528";

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

/** Fill and submit the one-screen broadcast form. Returns the new request id. */
async function fileRequest(page: Page, cargo: string): Promise<number> {
  await page.goto("/cabinet/logistics/requests/new");

  const form = page.getByTestId("logistics-request-form");
  await expect(form).toBeVisible();
  await page.getByLabel(/cargo name|наименование груза|yuk nomi/i).fill(cargo);
  await page.getByLabel(/^(volume|объём|hajmi)/i).fill("120");

  const selects = form.getByRole("combobox");
  await selects.nth(0).selectOption("containers");
  await selects.nth(1).selectOption("CN");
  await selects.nth(2).selectOption("UZ");

  await page.getByTestId("logistics-request-submit").click();
  await page.waitForURL(/\/cabinet\/logistics\/requests\/\d+\/done/, { timeout: 15_000 });

  const match = /\/cabinet\/logistics\/requests\/(\d+)\/done/.exec(page.url());
  return Number(match?.[1]);
}

test("a broadcast request reaches a carrier, who replies in a private thread", async ({
  page,
  request,
}) => {
  const cargo = `E2E ${Date.now()}`;

  // ── Buyer files it. No carrier is chosen anywhere in the flow. ────────────
  await login(page, request, uniquePhone());
  await registerCompany(page, uniqueTaxId());
  const requestId = await fileRequest(page, cargo);

  // A buyer's Заявки is the purchase-request module, untouched by any of this.
  await page.goto("/cabinet/requests");
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(
    /перевозку|transport|tashish/i,
  );

  // ── Carrier sees it in the pool at the SAME url. ──────────────────────────
  await page.context().clearCookies();
  await login(page, request, CARRIER_PHONE);
  await page.goto("/cabinet/requests");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /перевозку|transport|tashish/i,
  );
  // The pool's own chrome, not the buyer page with different rows in it.
  await expect(page.getByText(/мои отклики|my replies|mening javoblarim/i)).toBeVisible();

  const card = page.locator(`[data-request-id="${requestId}"]`);
  await expect(card).toBeVisible();
  await expect(card).toContainText(cargo);

  // ── Reply opens a thread and the chat. ───────────────────────────────────
  await page.getByTestId(`logistics-reply-${requestId}`).click();
  const chat = card.getByRole("log");
  await expect(chat).toBeVisible();

  await card.getByPlaceholder(/сообщение|message|xabar/i).fill("1450 USD за контейнер");
  await card.getByRole("button", { name: /отправить|send|yuborish/i }).click();
  await expect(chat).toContainText("1450 USD за контейнер");

  // The card now offers the room rather than starting one.
  await expect(page.getByTestId(`logistics-open-${requestId}`)).toBeVisible();
});
