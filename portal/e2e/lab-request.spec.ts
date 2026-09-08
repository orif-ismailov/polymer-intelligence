import { expect, test, type Page } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * «Заявка на исследование» — broadcast, then a private conversation.
 *
 * The logistics spec one domain over, with one difference that is the point of
 * this file: `/cabinet/requests` is now a THREE-way branch, and each of the
 * three failure modes is silent. A carrier landing on the lab pool, a lab
 * landing on the carrier pool, and either landing on the buyer's purchase-request
 * module all look like "an empty list", not like an error — so all three are
 * asserted rather than inferred from the one that happens to be under test.
 *
 * Requires a live migrated+seeded API on :8000 with the dev-only
 * the seeded demo logins, and at least one verified company holding a
 * CONFIRMED `laboratory` role (`seed_showcase` provides two).
 *
 * Signs in as a SPECIFIC seeded account: a laboratory has to be a member of a
 * company whose role staff have confirmed, which a freshly-registered throwaway
 * company is not. The same seeded account every run — sign-in is a password now, with no
 * per-account cooldown to trip over. Override with `PORTAL_LAB_LOGIN`.
 */

const DEMO_PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "demo-password-2026";
const LAB = {
  login: process.env.PORTAL_LAB_LOGIN ?? "cptl_lab-owner",
  password: DEMO_PASSWORD,
};
const CARRIER = {
  login: process.env.PORTAL_CARRIER_LOGIN ?? "trans_asia-owner",
  password: DEMO_PASSWORD,
};

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

/** Walk both sheets of the wizard. Returns the new request id. */
async function fileRequest(page: Page, product: string): Promise<number> {
  await page.goto("/cabinet/lab/requests/new");

  const form = page.getByTestId("lab-request-form");
  await expect(form).toBeVisible();

  // Sheet 1 — «Новая заявка»: what to test.
  await page
    .getByLabel(/what are we testing|что исследуем|nimani tekshiramiz/i)
    .fill(product);
  await page.getByTestId("lab-method-mfi").check();
  await page.getByTestId("lab-method-density").check();
  await page.getByTestId("lab-request-next").click();

  // Sheet 2 — «Данные для заявки»: who to come back to.
  await expect(page.getByTestId("lab-request-submit")).toBeVisible();
  await page
    .getByLabel(/contact person|контактное лицо|aloqa uchun shaxs/i)
    .fill("E2E QA");
  await page.getByTestId("lab-request-submit").click();

  await page.waitForURL(/\/cabinet\/lab\/requests\/\d+\/done/, {
    timeout: 15_000,
  });
  const match = /\/cabinet\/lab\/requests\/(\d+)\/done/.exec(page.url());
  return Number(match?.[1]);
}

test("a broadcast request reaches a laboratory, which replies in a private thread", async ({
  page,
  request,
}) => {
  const product = `E2E HDPE ${Date.now()}`;

  // ── Buyer files it. No laboratory is chosen anywhere in the flow. ─────────
  await login(page, await provisionAccount(request));
  await registerCompany(page, uniqueTaxId());
  const requestId = await fileRequest(page, product);

  await expect(page.getByTestId("lab-request-done")).toBeVisible();

  // A buyer's Заявки is still the purchase-request module, untouched by any of
  // this — neither pool may have taken the page over.
  await page.goto("/cabinet/requests");
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(
    /исследовани|analysis|tadqiqot/i,
  );
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(
    /перевозку|transport|tashish/i,
  );

  // ── The laboratory sees it in the pool at the SAME url. ──────────────────
  // The SEEDED lab account: its role is confirmed, which a company registered a
  // moment ago is not, and the pool is role-gated.
  await page.context().clearCookies();
  await login(page, LAB);
  await page.goto("/cabinet/requests");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /исследовани|analysis|tadqiqot/i,
  );
  // The pool's own chrome, not the buyer page with different rows in it.
  await expect(
    page.getByText(/мои отклики|my replies|mening javoblarim/i),
  ).toBeVisible();

  const card = page.locator(`[data-request-id="${requestId}"]`);
  await expect(card).toBeVisible();
  await expect(card).toContainText(product);

  // ── Reply opens a thread and the chat. ───────────────────────────────────
  await page.getByTestId(`lab-reply-${requestId}`).click();
  const chat = card.getByRole("log");
  await expect(chat).toBeVisible();

  await card
    .getByPlaceholder(/сообщение|message|xabar/i)
    .fill("ПТР + плотность, 2 дня");
  await card.getByRole("button", { name: /отправить|send|yuborish/i }).click();
  await expect(chat).toContainText("ПТР + плотность, 2 дня");

  // The card now offers the room rather than starting one.
  await expect(page.getByTestId(`lab-open-${requestId}`)).toBeVisible();
});

test("the third branch: a carrier still gets the carrier pool, not the lab one", async ({
  page,
}) => {
  await login(page, CARRIER);
  await page.goto("/cabinet/requests");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /перевозку|transport|tashish/i,
  );
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(
    /исследовани|analysis|tadqiqot/i,
  );
});
