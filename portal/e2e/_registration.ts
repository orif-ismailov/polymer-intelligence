import { expect, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

/** Phone-OTP sign-in, reading the code through the dev-only peek hook. */
export async function login(
  page: Page,
  request: APIRequestContext,
  phone: string,
): Promise<void> {
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

/**
 * Shared driver for the 5-step company-registration flow
 * («Тип компании → Данные → Банк → Документы → Проверка»).
 *
 * Three specs walk this flow to reach the surface they actually test, and they
 * had three drifting copies of it. Not a `*.spec.ts`, so Playwright's testMatch
 * does not collect it as a suite.
 */

const SKIP = /skip|пропустить|o.tkazib/i;

/** Step 1 — pick an account type. Registration involves no E-IMZO at all. */
export async function stepAccountType(
  page: Page,
  opts: { type?: string } = {},
): Promise<void> {
  await page.goto("/cabinet/companies/new/1");
  await page.getByTestId(`account-type-${opts.type ?? "distributor"}`).click();

  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/2");
}

/**
 * Step 2 — «Основная информация», opening with the ИНН.
 *
 * The registry lookup keys off that field, so on a deployment with the Didox
 * rail on, several of the values typed below arrive already filled; filling them
 * anyway is harmless and keeps the helper working on a stub deployment too.
 */
export async function stepDetails(page: Page, taxId?: string): Promise<void> {
  const name = page.getByLabel(/company name|название компании|kompaniya nomi/i);
  if (await name.isEditable()) {
    await name.fill("OOO E2E Test");
  }

  if (taxId != null) {
    const tax = page.getByLabel(/tax id|инн|stir/i).first();
    if (await tax.isEditable()) await tax.fill(taxId);
  }

  await page.getByLabel(/legal address|юридический адрес|yuridik manzil/i).first().fill("Tashkent, Amir Temur 123");
  await page.getByLabel(/registration date|дата регистрации|ro.yxatdan o.tgan sana/i).fill("2020-03-12");
  await page.getByLabel(/ownership form|форма собственности|mulkchilik shakli/i).selectOption("ООО");

  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3", { timeout: 20_000 });
}

/** Step 3 — bank (skipped) and step 4 — the required registration certificate. */
export async function stepBankAndDocuments(page: Page): Promise<void> {
  await page.getByRole("button", { name: SKIP }).click();
  await page.waitForURL("**/cabinet/companies/new/4");

  await page.setInputFiles('input[type="file"]', {
    name: "registration.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test document"),
  });
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/5");
}

/**
 * Step 5 — «Проверка компании». Arriving submits the case; the CTA unlocks once
 * the company exists, and continuing lands on «Регистрация завершена!».
 */
export async function stepReview(page: Page): Promise<number> {
  const submit = page.getByTestId("wizard-submit");
  await expect(submit).toBeEnabled({ timeout: 20_000 });
  await submit.click();

  await page.waitForURL(/\/cabinet\/companies\/new\/done\/\d+/, { timeout: 15_000 });
  await expect(page.getByTestId("wizard-done")).toBeVisible();

  const match = /\/cabinet\/companies\/new\/done\/(\d+)/.exec(page.url());
  return Number(match?.[1]);
}

/**
 * Confirm a registered company's identity with E-IMZO, from «Статус проверки».
 *
 * This is now the ONLY door to `identity_locked` — registration no longer signs
 * anything — and with `verification_auto_approve` on it is also how a spec gets a
 * company that may transact. Needs a stub bridge on `window.__EIMZO_BRIDGE__`
 * whose certificate INN matches `taxId`.
 */
export async function confirmIdentityWithEimzo(page: Page, companyId: number): Promise<void> {
  await page.goto(`/cabinet/companies/${companyId}/verification`);
  await page.getByTestId("eimzo-open").click();
  // NOT `eimzo-success`: confirming refetches the company, `identity_locked`
  // flips, and the whole offer block — button, dialog and that success alert —
  // unmounts. The alert is therefore racing its own side effect. The confirmed
  // badge is the state that persists, so it is what this waits on.
  await expect(page.getByTestId("eimzo-confirmed")).toBeVisible({ timeout: 20_000 });
}

/**
 * The whole flow, end to end. Returns the new company's id.
 *
 * `sign` no longer happens inside the wizard: it registers first, then confirms
 * on the verification screen — which is the real user path since E-IMZO left
 * registration, and the only one that still yields a verified company.
 */
export async function registerCompany(
  page: Page,
  taxId: string,
  opts: { type?: string; sign?: boolean } = {},
): Promise<number> {
  await stepAccountType(page, opts);
  await stepDetails(page, taxId);
  await stepBankAndDocuments(page);
  const companyId = await stepReview(page);
  if (opts.sign) await confirmIdentityWithEimzo(page, companyId);
  return companyId;
}
