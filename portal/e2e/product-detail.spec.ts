import {
  expect,
  test,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";

import { login, registerCompany } from "./_registration";

/**
 * The product sheet (`docs/new-design/product_detail.jpeg`), control by control.
 *
 * This page had no coverage at all — `r2-portal.spec.ts` only asserted that
 * `/market` renders an `h1`, so nothing had ever clicked a button on the detail
 * sheet. What it checks is what the audit found broken: «Мои запросы» refreshes
 * without a reload, the heart survives F5, the documents badge is a translated
 * label rather than a raw enum, a quantity that cannot reach the wire is caught
 * before the round trip, the contract cell hands the seller over, and the escrow
 * cell no longer pretends to start something the backend has no door for.
 *
 * Two browser contexts play the seller and the buyer; staff approval happens over
 * the admin API, because there is no self-serve way to make an offer public.
 *
 * Prerequisites (a live dev stack — CI runs no backend for this suite):
 *   - backend on :8000 with DEBUG=true (dev OTP peek) and EIMZO_STUB=true
 *   - app-setting verification_auto_approve=on, so onboarding yields a verified
 *     company (publishing an offer is gated on verification)
 *   - seeded staff (`seed_staff`) — the admin approves the offer
 *   - OTP_MAX_SENDS_PER_DAY raised: the cap is per client IP as well as per phone
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";
const BASE_URL = process.env.PORTAL_BASE_URL ?? "http://localhost:5173";
const ADMIN_EMAIL = process.env.SEED_ADMIN_EMAIL ?? "admin@polymer.uz";
const ADMIN_PASSWORD = process.env.SEED_ADMIN_PASSWORD ?? "admin_dev_password_change_in_prod";

const PDF = { mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 test document") };

const MY_INQUIRIES = /my inquiries|мои запросы|mening so/i;

function uniquePhone(): string {
  return `+998${String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0")}`;
}

function uniqueTaxId(): string {
  return String(320_000_000 + Math.floor(Math.random() * 79_999_999));
}

/** The R3 CAPIWS stub — onboarding signs with E-IMZO to come out verified. */
async function stubEimzo(context: BrowserContext, tin: string): Promise<void> {
  await context.addInitScript(
    (t) => {
      (window as unknown as { __EIMZO_BRIDGE__: unknown }).__EIMZO_BRIDGE__ = {
        probe: async () => true,
        listCertificates: async () => [
          { id: "k1", subjectName: "OOO " + t, tin: t, name: "DIRECTOR" },
        ],
        sign: async (_id: string, challenge: string) =>
          btoa(JSON.stringify({ challenge, tin: t, name: "DIRECTOR", org_name: "OOO " + t })),
      };
    },
    tin,
  );
}

/**
 * Publish an offer through the add-product wizard and return its id.
 *
 * Terms are set deliberately: samples available (so the sample block is live),
 * ready to sign a contract (so the contract cell is reachable), escrow left off
 * (so the escrow cell's "not offered" branch is the one under test). `acceptsRfq`
 * is opt-OUT in the sheet, which is why the caller can only turn it off.
 */
async function publishOffer(
  page: Page,
  name: string,
  opts: { acceptsRfq?: boolean } = {},
): Promise<number> {
  await page.goto("/offers/new/1");
  await expect(page.getByTestId("offer-wizard-step-1")).toBeVisible();

  // 1 — «Информация»
  await page.getByTestId("offer-wizard-product").selectOption("other");
  await page.getByTestId("offer-wizard-product-text").fill(name);
  await page.getByTestId("offer-wizard-next").click();

  // 2 — AI check: the sheet gates «Далее» on the verdict settling.
  await expect(page.getByTestId("offer-wizard-verdict")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("offer-wizard-next").click();

  // 3 — «Наличие»: in stock owes a quantity and a price.
  await expect(page.getByTestId("offer-wizard-step-3")).toBeVisible();
  await page.getByTestId("offer-wizard-qty").fill("500");
  await page.getByTestId("offer-wizard-price").fill("1020");
  await page.getByTestId("offer-wizard-next").click();

  // 4 — «Документы»: SDS + TDS are required. The TDS is what the documents tab
  // paints a badge for, and that badge is one of the things under test.
  await expect(page.getByTestId("offer-wizard-step-4")).toBeVisible();
  const files = page.locator('input[type="file"]');
  await files.nth(0).setInputFiles({ name: "SDS.pdf", ...PDF });
  await files.nth(1).setInputFiles({ name: "TDS.pdf", ...PDF });
  await page.getByTestId("offer-wizard-next").click();

  // 5 — «Лабораторные данные»: no passport is a complete answer.
  await expect(page.getByTestId("offer-wizard-step-5")).toBeVisible();
  await page.getByTestId("offer-wizard-no-passport").click();
  await page.getByTestId("offer-wizard-next").click();

  // 6 — «Условия продажи»
  await expect(page.getByTestId("offer-wizard-step-6")).toBeVisible();
  // Segmented: «Доступны» is the first cell, «Не предоставляются» the second.
  await page.getByTestId("offer-wizard-samples").getByRole("button").first().click();
  await page.getByLabel(/D-Doc/i).check();
  if (opts.acceptsRfq === false) await page.getByLabel(/RFQ/i).uncheck();
  await page.getByTestId("offer-wizard-next").click();

  // 7 — «Дополнительная информация»
  await expect(page.getByTestId("offer-wizard-step-7")).toBeVisible();
  await page.getByTestId("offer-wizard-description").fill("Полипропилен для литья под давлением.");
  await page.getByTestId("offer-wizard-next").click();

  // 8 — preview → publish
  await expect(page.getByTestId("offer-wizard-step-preview")).toBeVisible();
  await page.getByTestId("offer-wizard-publish").click();
  await page.waitForURL(/\/offers\/new\/done\/\d+/, { timeout: 30_000 });

  return Number(/\/offers\/new\/done\/(\d+)/.exec(page.url())?.[1]);
}

/** Staff approval — the only door that makes an offer public. */
async function approveOffer(request: APIRequestContext, offerId: number): Promise<void> {
  const auth = await request.post(`${API_BASE}/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  expect(auth.ok(), "the seeded admin must be able to sign in").toBeTruthy();
  const { access_token: token } = (await auth.json()) as { access_token: string };

  const res = await request.post(`${API_BASE}/admin/moderation/offers/${offerId}/approve`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {},
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}

/** A signed-in, verified buyer looking at `offerId`. */
async function openAsBuyer(
  browser: Browser,
  request: APIRequestContext,
  offerId: number,
): Promise<{ context: BrowserContext; page: Page }> {
  const tax = uniqueTaxId();
  const context = await browser.newContext({ baseURL: BASE_URL });
  await stubEimzo(context, tax);
  const page = await context.newPage();
  await login(page, request, uniquePhone());
  await registerCompany(page, tax, { type: "buyer", sign: true });

  await page.goto(`/market/${offerId}`);
  await expect(page.getByTestId("product-detail")).toBeVisible();
  return { context, page };
}

/** A verified seller with one published offer, awaiting or past approval. */
async function sellWith(
  browser: Browser,
  request: APIRequestContext,
  name: string,
  opts: { acceptsRfq?: boolean } = {},
): Promise<{ offerId: number; taxId: string }> {
  const taxId = uniqueTaxId();
  const context = await browser.newContext({ baseURL: BASE_URL });
  await stubEimzo(context, taxId);
  const page = await context.newPage();
  await login(page, request, uniquePhone());
  await registerCompany(page, taxId, { type: "supplier", sign: true });

  const offerId = await publishOffer(page, `${name} ${taxId}`, opts);
  await approveOffer(request, offerId);
  await context.close();
  return { offerId, taxId };
}

test("every control on the product sheet does what its label says", async ({ browser, request }) => {
  test.setTimeout(240_000);

  const { offerId, taxId } = await sellWith(browser, request, "PP H030 GP");
  const { context, page } = await openAsBuyer(browser, request, offerId);

  await expect(page.getByTestId("product-detail-hero")).toContainText(taxId);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(taxId);

  // ── Documents tab: a translated label, not the raw enum ─────────────────────
  await page.getByRole("button", { name: /^documents|^документы|^hujjatlar/i }).click();
  const tds = page.getByRole("link", { name: /TDS\.pdf/i });
  await expect(tds).toBeVisible();
  // The badge used to read "tds": `documentKind` is the company-verification tree
  // (bank letter, director ID …) and carries no offer file kinds at all.
  await expect(tds).toContainText(
    /Техническая спецификация|Technical data sheet|Texnik spetsifikatsiya/i,
  );

  // ── Favourite: responds to the tap, and survives a reload ───────────────────
  await page.getByRole("button", { name: /^description|^описание|^tavsif/i }).click();
  const heart = page.getByTestId("product-detail-favorite");
  await expect(heart).toHaveAttribute("aria-pressed", "false");
  await heart.click();
  await expect(heart).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByTestId("product-detail-favorite")).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  // ── Inquiry validation: the wire wants a positive number ────────────────────
  const submit = page.getByTestId("inquiry-submit");
  const qty = page.getByLabel(/quantity|нужный объём|kerakli hajm/i);
  await qty.fill("500 тонн");
  await expect(submit).toBeDisabled();

  // ── Sending an inquiry refreshes «Мои запросы» in place ─────────────────────
  await expect(page.getByText(MY_INQUIRIES)).toHaveCount(0);
  await qty.fill("12");
  await page.getByLabel(/^message|^сообщение|^xabar/i).fill("Прошу коммерческое предложение.");
  await expect(submit).toBeEnabled();
  await submit.click();
  // No reload between the click and this assertion — that is the whole point.
  await expect(page.getByText(MY_INQUIRIES)).toBeVisible({ timeout: 15_000 });

  // ── The sticky bar ──────────────────────────────────────────────────────────
  const cells = page.getByTestId("product-detail-action-bar").getByRole("button");
  // Escrow is the third cell. The seller left escrow off, so it says so instead
  // of scrolling to the inquiry form the way the first cell does.
  await expect(cells.nth(2)).toBeDisabled();

  // Contract hands the seller over, so /contracts/new needs no name guessing.
  await cells.nth(1).click();
  await page.waitForURL(/\/contracts\/new\?/);
  const url = new URL(page.url());
  expect(url.searchParams.get("offerId")).toBe(String(offerId));
  expect(Number(url.searchParams.get("counterpartyId"))).toBeGreaterThan(0);
  // Preselected by id, not typed: the seller is already named on the sheet.
  await expect(page.getByText(new RegExp(taxId))).toBeVisible({ timeout: 15_000 });

  await context.close();
});

test("an offer that refuses RFQs offers no way to send one", async ({ browser, request }) => {
  test.setTimeout(240_000);

  const { offerId } = await sellWith(browser, request, "PP NO-RFQ", { acceptsRfq: false });
  const { context, page } = await openAsBuyer(browser, request, offerId);

  // The hero CTA was already disabled; the form below it used to submit anyway,
  // and the bar's message cell scrolled the buyer straight to it.
  await expect(page.getByTestId("product-detail-rfq")).toBeDisabled();
  await expect(page.getByTestId("inquiry-submit")).toHaveCount(0);
  await expect(
    page.getByTestId("product-detail-action-bar").getByRole("button").first(),
  ).toBeDisabled();

  await context.close();
});
