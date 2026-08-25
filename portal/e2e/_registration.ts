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

/** Step 1 — pick an account type and (optionally) sign with E-IMZO. */
export async function stepAccountType(
  page: Page,
  opts: { type?: string; sign?: boolean } = {},
): Promise<void> {
  await page.goto("/cabinet/companies/new/1");
  await page.getByTestId(`account-type-${opts.type ?? "distributor"}`).click();

  if (opts.sign) {
    // The PIN gates the CTA exactly as the sheet draws it; the E-IMZO module
    // prompts for the real one, so any value unlocks the button here.
    //
    // `getByRole("textbox")`, not `getByLabel(/pin/i)`: the field ships with a
    // «Показать PIN-код» reveal button beside it, so the bare label regex matches
    // TWO elements and every spec that registers a company dies on a strict-mode
    // violation — sixteen of them, all reported as unrelated feature failures.
    await page.getByRole("textbox", { name: /pin/i }).fill("123456");
    await page.getByTestId("wizard-eimzo").click();
    await expect(page.getByTestId("eimzo-success")).toBeVisible({ timeout: 15_000 });
  }

  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/2");
}

/**
 * Step 2 — «Основная информация». Every field is required, so a signed company
 * (name + tax id frozen and disabled) still has to state its form and date.
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
  await page.waitForURL("**/cabinet/companies/new/3");
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

/** The whole flow, end to end. Returns the new company's id. */
export async function registerCompany(
  page: Page,
  taxId: string,
  opts: { type?: string; sign?: boolean } = {},
): Promise<number> {
  await stepAccountType(page, opts);
  await stepDetails(page, opts.sign ? undefined : taxId);
  await stepBankAndDocuments(page);
  return stepReview(page);
}
