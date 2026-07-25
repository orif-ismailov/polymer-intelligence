import { expect, test, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";

/**
 * R3 Stage B e2e: the full contract demo with a STUBBED CAPIWS bridge.
 *
 * Prerequisites (a live dev stack): backend with EIMZO_STUB=true AND the app-setting
 * verification_auto_approve=on (so E-IMZO onboarding yields a verified company that
 * can transact), the SUPPLY_V1 template seeded, and the dev OTP peek endpoint.
 * Two browser contexts play the two companies. Valid harness; not run in CI here.
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
  await page.goto("/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();
  await page.waitForURL("**/login/code");
  await page.getByLabel(/code|код|kod/i).fill(await readOtp(request, phone));
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

/** Create + E-IMZO-verify a company (auto-approve assumed on). */
async function onboardVerified(page: Page, tax: string): Promise<void> {
  await page.goto("/companies/new/1");
  await page.getByLabel(/tax id|инн|stir/i).fill(tax);
  await page.getByTestId("wizard-eimzo").click();
  await page.waitForURL(/\/companies\/\d+\/verification/, { timeout: 15_000 });
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
  await pageA.goto("/contracts/new");
  await pageA.getByTestId("contracts-new").isVisible().catch(() => undefined);
  // template select (first non-empty option) + product field
  await pageA.locator("select").first().selectOption({ index: 1 });
  const productInput = pageA.getByLabel(/product|товар|tovar/i).first();
  if (await productInput.count()) await productInput.fill("HDPE film");
  // counterparty search → pick B
  await pageA.getByPlaceholder(/search|поиск|qidirish/i).fill(taxB);
  await pageA.getByTestId("cp-option").first().click();
  await pageA.getByTestId("contract-submit").click();
  await pageA.waitForURL(/\/contracts\/\d+/);
  const contractUrl = pageA.url();

  // A sends → pending_counterparty
  await pageA.getByTestId("contract-send").click();
  await expect(pageA.getByText(/awaiting counterparty|ожидает контрагента|kontragent kutil/i)).toBeVisible();

  // B opens the same contract, accepts, signs
  const contractId = contractUrl.split("/").pop();
  await pageB.goto(`/contracts/${contractId}`);
  await pageB.getByTestId("contract-accept").click();
  await pageB.getByRole("button", { name: /sign|подписать|imzolash/i }).first().click();
  await expect(pageB.getByTestId("eimzo-success")).toBeVisible({ timeout: 15_000 });

  // A signs → active
  await pageA.goto(`/contracts/${contractId}`);
  await pageA.getByRole("button", { name: /sign|подписать|imzolash/i }).first().click();
  await expect(pageA.getByTestId("eimzo-success")).toBeVisible({ timeout: 15_000 });
  await pageA.reload();
  await expect(pageA.getByText(/active|активен|faol/i).first()).toBeVisible();
  await expect(pageA.getByTestId("contract-download")).toBeVisible();

  await ctxA.close();
  await ctxB.close();
});
