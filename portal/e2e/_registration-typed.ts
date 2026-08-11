import { expect, type Page } from "@playwright/test";

/**
 * Drivers for the three TYPED registration wizards (manufacturer/logistics/
 * laboratory), which `_registration.ts` does not cover — that file only walks
 * the shared 5-step "default" flow (buyer/distributor). Written for the
 * end-to-end registration audit: as of this writing no existing spec drives
 * these three wizards through the real UI (role-gating.spec.ts exercises their
 * post-registration NAV shape using pre-seeded phones, never the wizard
 * itself).
 *
 * Every step's submit button is `data-testid="wizard-next"` regardless of
 * step/type, so steps are driven generically where possible.
 */

async function next(page: Page, expectStep: number): Promise<void> {
  await page.getByTestId("wizard-next").click();
  await page.waitForURL(`**/cabinet/companies/new/${expectStep}`);
  // The portal SSRs cabinet routes and a hydration mismatch is logged on every
  // navigation (found via this audit — see report); interacting with a toggle
  // button immediately after navigation can race the post-hydration remount
  // and silently lose the click's state update. Settling briefly avoids that
  // race in the driver; the mismatch itself is reported as a defect, not
  // worked around in the app.
  await page.waitForLoadState("networkidle");
}

async function uploadPdf(page: Page, name = "registration.pdf"): Promise<void> {
  // Dropzones mount together but not synchronously with the route change;
  // grabbing `input[type=file]` immediately after `waitForURL` can catch the
  // DOM mid-render. Wait for the shared placeholder text so every dropzone
  // (registration_certificate first) has actually mounted before indexing.
  await page.getByText(/загрузить документ|upload document/i).first().waitFor({ state: "visible" });
  const inputs = page.locator('input[type="file"]');
  // The registration_certificate dropzone is always first when unlocked.
  await inputs.nth(0).setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test document"),
  });
  await expect(page.getByText(name)).toBeVisible();
}

function section(page: Page, headingText: string) {
  return page.locator("section", { hasText: headingText });
}

/** Step 1, shared: pick the account-type card. */
export async function pickAccountType(page: Page, type: string): Promise<void> {
  await page.goto("/cabinet/companies/new/1");
  await page.waitForLoadState("networkidle");
  await page.getByTestId(`account-type-${type}`).click();
  await next(page, 2);
}

// ── Manufacturer (7 steps) ──────────────────────────────────────────────────

export async function manufacturerDetails(page: Page, taxId: string): Promise<void> {
  await page.getByLabel(/юридическое название завода|factory legal name/i).fill("OOO E2E Factory");
  await page.getByLabel(/ИНН \(СТИР\)|tax id/i).first().fill(taxId);
  await page.getByLabel(/регистрационный номер компании|registration number/i).fill(`REG-${taxId}`);
  await page.getByLabel(/юридический адрес|legal address/i).first().fill("Tashkent, Chilanzar 5");
  await page.getByLabel(/фактический адрес завода|factory address/i).fill("Tashkent, Industrial Zone 12");
  await next(page, 3);
}

export async function manufacturerProduction(page: Page): Promise<void> {
  await page.getByLabel(/вид производства|production type/i).selectOption({ index: 1 });
  await page.getByLabel(/основная продукция|main products/i).selectOption({ index: 1 });
  await page.getByLabel(/годовая производственная мощность|annual capacity/i).fill("1000");
  await page.getByLabel(/количество производственных линий|production lines/i).fill("2");
  await page.getByLabel(/количество сотрудников|employees/i).fill("50");
  // Markets defaults to ["domestic"] (draftStore.ts) — already satisfies the
  // "at least one market" rule, so no click needed; clicking "Внутренний
  // рынок" here would DESELECT the default and leave markets empty.
  await page.getByLabel(/год основания завода|founded year/i).selectOption({ index: 1 });
  await next(page, 4);
}

export async function manufacturerCatalog(page: Page): Promise<void> {
  await page.getByTestId("wizard-catalog-manual").click();
  await page.waitForURL("**/cabinet/companies/new/5");
}

export async function manufacturerCerts(page: Page): Promise<void> {
  await uploadPdf(page);
  await next(page, 6);
}

export async function manufacturerBuyerRequirements(page: Page): Promise<void> {
  await page.getByLabel(/минимальный объём \(moq\)|moq/i).fill("10");
  await next(page, 7);
}

export async function manufacturerReview(page: Page): Promise<number> {
  await page.getByTestId("wizard-almost-ready").waitFor();
  await page.getByTestId("wizard-submit-moderation").click();
  const submit = page.getByTestId("wizard-submit");
  await expect(submit).toBeEnabled({ timeout: 20_000 });
  await submit.click();
  await page.waitForURL(/\/cabinet\/companies\/new\/done\/\d+/, { timeout: 15_000 });
  await expect(page.getByTestId("wizard-done")).toBeVisible();
  return Number(/\/done\/(\d+)/.exec(page.url())?.[1]);
}

export async function registerManufacturer(page: Page, taxId: string): Promise<number> {
  await pickAccountType(page, "manufacturer");
  await manufacturerDetails(page, taxId);
  await manufacturerProduction(page);
  await manufacturerCatalog(page);
  await manufacturerCerts(page);
  await manufacturerBuyerRequirements(page);
  return manufacturerReview(page);
}

// ── Logistics (7 steps) ─────────────────────────────────────────────────────

export async function logisticsDetails(page: Page, taxId: string): Promise<void> {
  await page.getByLabel(/название компании|company name/i).fill("OOO E2E Carrier");
  await page.getByLabel(/город|city/i).fill("Tashkent");
  await page.getByLabel(/ИНН \/ Регистрационный номер|tax id.*registration/i).fill(taxId);
  await page.getByLabel(/юридический адрес|legal address/i).first().fill("Tashkent, Yunusabad 8");
  await next(page, 3);
}

export async function logisticsServices(page: Page): Promise<void> {
  await page
    .getByRole("group", { name: "Услуги логистической компании" })
    .locator("button")
    .first()
    .click();
  await next(page, 4);
}

export async function logisticsGeography(page: Page): Promise<void> {
  await section(page, "Откуда (страны-поставщики)").locator("button").first().click();
  await section(page, "Куда (страны-получатели)").locator("button").first().click();
  await next(page, 5);
}

export async function logisticsSpecialization(page: Page): Promise<void> {
  await section(page, "Какие грузы вы перевозите?").locator("button").first().click();
  await next(page, 6);
}

export async function logisticsTariffsDocs(page: Page): Promise<void> {
  await section(page, "Тарифы").locator('input[type="radio"]').first().click();
  await uploadPdf(page);
  await next(page, 7);
}

export async function logisticsReview(page: Page): Promise<number> {
  const submit = page.getByTestId("wizard-submit");
  await expect(submit).toBeEnabled({ timeout: 20_000 });
  await submit.click();
  await page.waitForURL(/\/cabinet\/companies\/new\/done\/\d+/, { timeout: 15_000 });
  await expect(page.getByTestId("wizard-done")).toBeVisible();
  return Number(/\/done\/(\d+)/.exec(page.url())?.[1]);
}

export async function registerLogistics(page: Page, taxId: string): Promise<number> {
  await pickAccountType(page, "logistics");
  await logisticsDetails(page, taxId);
  await logisticsServices(page);
  await logisticsGeography(page);
  await logisticsSpecialization(page);
  await logisticsTariffsDocs(page);
  return logisticsReview(page);
}

// ── Laboratory (4 steps) ─────────────────────────────────────────────────────

export async function laboratoryDetails(page: Page, taxId: string): Promise<void> {
  await page.getByLabel(/название лаборатории|laboratory name/i).fill("OOO E2E Lab");
  await page.getByLabel(/город|city/i).fill("Tashkent");
  await page.getByLabel(/ИНН \/ Регистрационный номер|tax id.*registration/i).fill(taxId);
  await page.getByLabel(/юридический адрес|legal address/i).first().fill("Tashkent, Mirzo Ulugbek 3");
  await page.getByLabel(/email/i).fill("lab-e2e@example.uz");
  await page.getByLabel(/телефон|phone/i).fill("+998901112233");
  await page.getByLabel(/описание|description/i).fill("E2E test laboratory profile description.");
  await next(page, 3);
}

export async function laboratoryLicenses(page: Page): Promise<void> {
  await uploadPdf(page);
  await next(page, 4);
}

export async function laboratoryReview(page: Page): Promise<number> {
  const submit = page.getByTestId("wizard-submit");
  await expect(submit).toBeEnabled({ timeout: 20_000 });
  await submit.click();
  await page.waitForURL(/\/cabinet\/companies\/new\/done\/\d+/, { timeout: 15_000 });
  await expect(page.getByTestId("wizard-done")).toBeVisible();
  return Number(/\/done\/(\d+)/.exec(page.url())?.[1]);
}

export async function registerLaboratory(page: Page, taxId: string): Promise<number> {
  await pickAccountType(page, "laboratory");
  await laboratoryDetails(page, taxId);
  await laboratoryLicenses(page);
  return laboratoryReview(page);
}

export function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

export function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}
