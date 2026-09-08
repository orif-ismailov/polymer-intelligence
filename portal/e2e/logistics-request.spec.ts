import { expect, test, type Page } from "@playwright/test";

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
 * the seeded demo logins, and at least one verified logistics company.
 *
 * Unlike the other specs, this one signs in as a SPECIFIC seeded account:
 * a carrier has to be a member of a company whose logistics role staff have
 * confirmed, which a freshly-registered throwaway company is not. That means the
 * same seeded account on every run; sign-in is a password, so there is no
 * cooldown to trip over. Override the account with `PORTAL_CARRIER_LOGIN`.
 */

const DEMO_PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "demo-password-2026";
const CARRIER = {
  login: process.env.PORTAL_CARRIER_LOGIN ?? "trans_asia-owner",
  password: DEMO_PASSWORD,
};

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
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
  await page.waitForURL(/\/cabinet\/logistics\/requests\/\d+\/done/, {
    timeout: 15_000,
  });

  const match = /\/cabinet\/logistics\/requests\/(\d+)\/done/.exec(page.url());
  return Number(match?.[1]);
}

test("a broadcast request reaches a carrier, who replies in a private thread", async ({
  page,
  request,
}) => {
  const cargo = `E2E ${Date.now()}`;

  // ── Buyer files it. No carrier is chosen anywhere in the flow. ────────────
  await login(page, await provisionAccount(request));
  await registerCompany(page, uniqueTaxId());
  const requestId = await fileRequest(page, cargo);

  // A buyer's Заявки is the purchase-request module, untouched by any of this.
  await page.goto("/cabinet/requests");
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(
    /перевозку|transport|tashish/i,
  );

  // ── Carrier sees it in the pool at the SAME url. ──────────────────────────
  // The SEEDED carrier: a confirmed role, which a brand-new company lacks.
  await page.context().clearCookies();
  await login(page, CARRIER);
  await page.goto("/cabinet/requests");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /перевозку|transport|tashish/i,
  );
  // The pool's own chrome, not the buyer page with different rows in it.
  await expect(
    page.getByText(/мои отклики|my replies|mening javoblarim/i),
  ).toBeVisible();

  const card = page.locator(`[data-request-id="${requestId}"]`);
  await expect(card).toBeVisible();
  await expect(card).toContainText(cargo);

  // ── Reply opens a thread and the chat. ───────────────────────────────────
  await page.getByTestId(`logistics-reply-${requestId}`).click();
  const chat = card.getByRole("log");
  await expect(chat).toBeVisible();

  await card
    .getByPlaceholder(/сообщение|message|xabar/i)
    .fill("1450 USD за контейнер");
  await card.getByRole("button", { name: /отправить|send|yuborish/i }).click();
  await expect(chat).toContainText("1450 USD за контейнер");

  // The card now offers the room rather than starting one.
  await expect(page.getByTestId(`logistics-open-${requestId}`)).toBeVisible();
});
