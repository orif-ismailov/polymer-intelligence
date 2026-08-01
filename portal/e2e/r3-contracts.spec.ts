import { expect, test, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * R3 Stage B e2e: the full contract demo with a STUBBED CAPIWS bridge.
 *
 * Prerequisites (a live dev stack):
 *   - backend on :8000 with DEBUG=true (dev OTP peek endpoint) and EIMZO_STUB=true
 *   - app-setting verification_auto_approve=on, so E-IMZO onboarding yields a
 *     verified company that can transact
 *   - the SUPPLY_V1 contract template seeded (seed_contract_templates)
 *   - OTP_MAX_SENDS_PER_DAY raised: the cap is enforced PER CLIENT IP as well as
 *     per phone, so the default 5 blocks repeated runs from one machine
 *
 * Two browser contexts play the two companies.
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";
const BASE_URL = process.env.PORTAL_BASE_URL ?? "http://localhost:5173";

function uniquePhone(): string {
  return `+998${String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0")}`;
}
function uniqueTaxId(): string {
  return String(300_000_000 + Math.floor(Math.random() * 99_999_999));
}

async function readOtp(request: APIRequestContext, phone: string): Promise<string> {
  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  const body = (await res.json()) as { code: string };
  return body.code;
}

async function stubEimzo(context: BrowserContext, tin: string): Promise<void> {
  await context.addInitScript(
    (t) => {
      (window as unknown as { __EIMZO_BRIDGE__: unknown }).__EIMZO_BRIDGE__ = {
        probe: async () => true,
        listCertificates: async () => [{ id: "k1", subjectName: "OOO " + t, tin: t, name: "DIRECTOR" }],
        sign: async (_id: string, challenge: string) =>
          btoa(JSON.stringify({ challenge, tin: t, name: "DIRECTOR", org_name: "OOO " + t })),
      };
    },
    tin,
  );
}

async function login(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.goto("/cabinet/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();
  await page.waitForURL("**/cabinet/login/code");
  await page.getByLabel(/code|код|kod/i).fill(await readOtp(request, phone));
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/cabinet/login"));
}

/**
 * Create + E-IMZO-verify a company (auto-approve assumed on).
 *
 * The signature now happens on step 1 and creates the company from the
 * certificate's STIR, but the verification CASE is only opened at the end of the
 * flow — so this walks the whole wizard rather than stopping at the signature.
 */
async function onboardVerified(page: Page, tax: string): Promise<void> {
  await registerCompany(page, tax, { type: "distributor", sign: true });
}

test("Stage B: two verified companies sign a contract end-to-end", async ({ browser, request }) => {
  const taxA = uniqueTaxId();
  const taxB = uniqueTaxId();
  const phoneA = uniquePhone();
  const phoneB = uniquePhone();

  const ctxA = await browser.newContext({ baseURL: BASE_URL });
  const ctxB = await browser.newContext({ baseURL: BASE_URL });
  await stubEimzo(ctxA, taxA);
  await stubEimzo(ctxB, taxB);
  const pageA = await ctxA.newPage();
  const pageB = await ctxB.newPage();

  // Onboard + verify both companies (E-IMZO, auto-approve on).
  await login(pageA, request, phoneA);
  await onboardVerified(pageA, taxA);
  await login(pageB, request, phoneB);
  await onboardVerified(pageB, taxB);

  // Company A creates a contract with company B.
  await pageA.goto("/cabinet/contracts/new");
  // Template select (first non-empty option), then fill EVERY field the template's
  // variables_schema renders — the form is schema-driven, so drive it generically
  // rather than naming fields (a template change must not silently skip a required one).
  const varsCard = pageA.getByTestId("contract-variables");
  await varsCard.locator("select").first().selectOption({ index: 1 });
  await expect(varsCard.locator("input")).not.toHaveCount(0);

  const selects = varsCard.locator("select");
  for (let i = 1; i < (await selects.count()); i++) {
    await selects.nth(i).selectOption({ index: 1 });
  }
  const inputs = varsCard.locator("input");
  for (let i = 0; i < (await inputs.count()); i++) {
    await inputs.nth(i).fill(i === 0 ? "HDPE film" : `e2e-${i}`);
  }

  // counterparty search → pick B
  await pageA.getByPlaceholder(/search|поиск|qidirish/i).fill(taxB);
  await pageA.getByTestId("cp-option").first().click();
  await pageA.getByTestId("contract-submit").click();
  await pageA.waitForURL(/\/cabinet\/contracts\/\d+/);
  const contractUrl = pageA.url();

  // A sends → pending_counterparty
  await pageA.getByTestId("contract-send").click();
  await expect(pageA.getByText(/awaiting counterparty|ожидает контрагента|kontragent kutil/i)).toBeVisible();

  // B opens the same contract, accepts, signs.
  // The dialog auto-signs (single stub cert) and, on success, the parent refetches —
  // which unmounts the sign button. So assert the DURABLE outcome (the recorded
  // signature + resulting state), not the transient success alert.
  const contractId = contractUrl.split("/").pop();
  await pageB.goto(`/cabinet/contracts/${contractId}`);
  await pageB.getByTestId("contract-accept").click();
  await pageB.getByTestId("eimzo-open").click();
  await expect(pageB.getByText(/awaiting the other|ожидаем подпись|ikkinchi tomon/i)).toBeVisible({
    timeout: 15_000,
  });
  await expect(pageB.getByTestId("eimzo-open")).toHaveCount(0);

  // A signs → both signatures present → active
  await pageA.goto(`/cabinet/contracts/${contractId}`);
  await pageA.getByTestId("eimzo-open").click();
  await expect(pageA.getByTestId("contract-download")).toBeVisible({ timeout: 15_000 });
  await pageA.reload();
  await expect(pageA.getByText(/active|активен|faol/i).first()).toBeVisible();
  await expect(pageA.getByTestId("contract-download")).toBeVisible();
  await expect(pageA.getByTestId("contract-pdf")).toBeVisible();

  await ctxA.close();
  await ctxB.close();
});
