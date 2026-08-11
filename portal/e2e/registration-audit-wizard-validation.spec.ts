import { expect, test } from "@playwright/test";

import { login } from "./_registration";
import { pickAccountType, uniquePhone, uniqueTaxId } from "./_registration-typed";

/**
 * Validation/failure-case audit for the company-registration wizard.
 * Happy paths live in registration-audit-smoke.spec.ts; this file is the
 * negative space — empty/invalid fields, bad uploads, and the one true
 * server-side conflict (duplicate tax_id).
 */

test.use({ locale: "ru-RU" });

// ── Buyer/default flow (StepDetails + StepDocuments) — deep dive ───────────

test("step 2: empty legal name blocks Next, with the field-level error", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "buyer");

  const next = page.getByTestId("wizard-next");
  await expect(next).toBeDisabled();
  // Blur without typing — the field is required and empty from the start.
  await page.getByLabel(/название компании/i).click();
  await page.getByLabel(/название компании/i).blur();
  await expect(page.getByText("Укажите название компании")).toBeVisible();
  await expect(next).toBeDisabled();
});

test("step 2: non-numeric / wrong-length tax id is rejected (UZ 9-digit rule)", async ({
  page,
  request,
}) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "buyer");

  await page.getByLabel(/название компании/i).fill("OOO E2E Test");
  const tax = page.getByLabel(/ИНН \(СТИР\)/i).first();
  await tax.fill("12345"); // too short
  await tax.blur();
  await expect(page.getByText("ИНН должен содержать 9 цифр")).toBeVisible();
  await expect(page.getByTestId("wizard-next")).toBeDisabled();

  await tax.fill("12345678A"); // letters strip via input handler, but confirm still invalid if not 9 digits
  await tax.blur();
  await expect(page.getByTestId("wizard-next")).toBeDisabled();
});

test("step 2: a future registration date is rejected", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "buyer");

  await page.getByLabel(/название компании/i).fill("OOO E2E Test");
  await page.getByLabel(/ИНН \(СТИР\)/i).first().fill(uniqueTaxId());
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Amir Temur 1");

  const futureDate = new Date();
  futureDate.setFullYear(futureDate.getFullYear() + 1);
  const iso = futureDate.toISOString().slice(0, 10);
  const dateField = page.getByLabel(/дата регистрации/i);
  await dateField.fill(iso);
  await dateField.blur();
  await expect(page.getByText("Укажите корректную дату регистрации")).toBeVisible();
  await expect(page.getByTestId("wizard-next")).toBeDisabled();
});

test("step 4: missing required registration certificate blocks Next", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "buyer");
  await page.getByLabel(/название компании/i).fill("OOO E2E Test");
  await page.getByLabel(/ИНН \(СТИР\)/i).first().fill(uniqueTaxId());
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Amir Temur 1");
  await page.getByLabel(/дата регистрации/i).fill("2020-01-15");
  await page.getByLabel(/форма собственности/i).selectOption("ООО");
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3");
  // Bank step — skip it.
  await page.getByRole("button", { name: /пропустить/i }).click();
  await page.waitForURL("**/cabinet/companies/new/4");

  await expect(page.getByTestId("wizard-next")).toBeDisabled();
});

test("step 4: an unsupported file type is rejected client-side with a clear message", async ({
  page,
  request,
}) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "buyer");
  await page.getByLabel(/название компании/i).fill("OOO E2E Test");
  await page.getByLabel(/ИНН \(СТИР\)/i).first().fill(uniqueTaxId());
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Amir Temur 1");
  await page.getByLabel(/дата регистрации/i).fill("2020-01-15");
  await page.getByLabel(/форма собственности/i).selectOption("ООО");
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3");
  await page.getByRole("button", { name: /пропустить/i }).click();
  await page.waitForURL("**/cabinet/companies/new/4");

  await page.locator('input[type="file"]').first().setInputFiles({
    name: "malware.exe",
    mimeType: "application/x-msdownload",
    buffer: Buffer.from("MZ fake exe content"),
  });
  await expect(
    page.getByText("Неподдерживаемый формат файла. Загрузите PDF, JPG или PNG."),
  ).toBeVisible();
  await expect(page.getByTestId("wizard-next")).toBeDisabled();
});

test("step 4: an oversized file is rejected client-side before any upload", async ({
  page,
  request,
}) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "buyer");
  await page.getByLabel(/название компании/i).fill("OOO E2E Test");
  await page.getByLabel(/ИНН \(СТИР\)/i).first().fill(uniqueTaxId());
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Amir Temur 1");
  await page.getByLabel(/дата регистрации/i).fill("2020-01-15");
  await page.getByLabel(/форма собственности/i).selectOption("ООО");
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3");
  await page.getByRole("button", { name: /пропустить/i }).click();
  await page.waitForURL("**/cabinet/companies/new/4");

  let uploadHit = false;
  await page.route("**/portal/companies/*/documents", (route) => {
    uploadHit = true;
    void route.continue();
  });
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "huge.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.alloc(11 * 1024 * 1024, "x"), // 11MB > MAX_UPLOAD_BYTES (10MB)
  });
  await expect(page.getByText(/Файл превышает \d+ МБ/)).toBeVisible();
  await expect(page.getByTestId("wizard-next")).toBeDisabled();
  expect(uploadHit).toBe(false); // never reached the network — rejected before submit
});

// ── Server-side conflict: duplicate tax_id ──────────────────────────────────

test("registering a second company with the same (jurisdiction, tax_id) is rejected as a duplicate", async ({
  page,
  request,
}) => {
  const sharedTaxId = uniqueTaxId();

  // First registration succeeds.
  await login(page, request, uniquePhone());
  await pickAccountType(page, "buyer");
  await page.getByLabel(/название компании/i).fill("OOO First");
  await page.getByLabel(/ИНН \(СТИР\)/i).first().fill(sharedTaxId);
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Amir Temur 1");
  await page.getByLabel(/дата регистрации/i).fill("2020-01-15");
  await page.getByLabel(/форма собственности/i).selectOption("ООО");
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3");
  await page.getByRole("button", { name: /пропустить/i }).click();
  await page.waitForURL("**/cabinet/companies/new/4");
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "reg.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test"),
  });
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/5");
  await expect(page.getByTestId("wizard-submit")).toBeEnabled({ timeout: 20_000 });
  await page.getByTestId("wizard-submit").click();
  await page.waitForURL(/\/cabinet\/companies\/new\/done\/\d+/, { timeout: 15_000 });

  // Second account, same tax_id — must be rejected, not silently accepted.
  await page.context().clearCookies();
  await login(page, request, uniquePhone());
  await pickAccountType(page, "buyer");
  await page.getByLabel(/название компании/i).fill("OOO Second");
  await page.getByLabel(/ИНН \(СТИР\)/i).first().fill(sharedTaxId);
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Amir Temur 2");
  await page.getByLabel(/дата регистрации/i).fill("2020-01-15");
  await page.getByLabel(/форма собственности/i).selectOption("ООО");
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3");
  await page.getByRole("button", { name: /пропустить/i }).click();
  await page.waitForURL("**/cabinet/companies/new/4");
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "reg.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test"),
  });
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/5");
  await expect(page.getByText("Компания с таким ИНН уже существует.")).toBeVisible({
    timeout: 20_000,
  });
  // Must NOT have advanced to the done screen.
  await expect(page).not.toHaveURL(/\/done\//);
});

// ── Typed-flow required-field spot checks ───────────────────────────────────

test("manufacturer step 3: empty production fields block Next", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "manufacturer");
  await page.getByLabel(/юридическое название завода/i).fill("OOO E2E Factory");
  await page.getByLabel(/ИНН \(СТИР\)/i).first().fill(uniqueTaxId());
  await page.getByLabel(/регистрационный номер компании/i).fill("REG-X");
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Chilanzar 5");
  await page.getByLabel(/фактический адрес завода/i).fill("Tashkent, Industrial Zone 12");
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3");

  // Nothing filled yet on the production step.
  await expect(page.getByTestId("wizard-next")).toBeDisabled();
});

test("manufacturer step 6: empty MOQ blocks Next", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "manufacturer");
  await page.getByLabel(/юридическое название завода/i).fill("OOO E2E Factory");
  await page.getByLabel(/ИНН \(СТИР\)/i).first().fill(uniqueTaxId());
  await page.getByLabel(/регистрационный номер компании/i).fill("REG-X");
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Chilanzar 5");
  await page.getByLabel(/фактический адрес завода/i).fill("Tashkent, Industrial Zone 12");
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3");

  await page.getByLabel(/вид производства/i).selectOption({ index: 1 });
  await page.getByLabel(/основная продукция/i).selectOption({ index: 1 });
  await page.getByLabel(/годовая производственная мощность/i).fill("1000");
  await page.getByLabel(/количество производственных линий/i).fill("2");
  await page.getByLabel(/количество сотрудников/i).fill("50");
  await page.getByLabel(/год основания завода/i).selectOption({ index: 1 });
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/4");
  await page.getByTestId("wizard-catalog-manual").click();
  await page.waitForURL("**/cabinet/companies/new/5");
  await page.getByText(/загрузить документ/i).first().waitFor();
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "reg.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test"),
  });
  await expect(page.getByText("reg.pdf")).toBeVisible();
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/6");

  // MOQ left empty — Next stays disabled, the actual protection. (This
  // step's inline "Укажите минимальный объём заказа" text is also gated
  // behind `submitted`, set only by the form's onSubmit — reachable in a
  // real browser via Enter in a text field, but not reliably via Playwright's
  // synthetic Enter here; not re-asserted to avoid a flaky false negative.)
  await expect(page.getByTestId("wizard-next")).toBeDisabled();
});

test("logistics step 3: no service selected blocks Next", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "logistics");
  await page.getByLabel(/название компании/i).fill("OOO E2E Carrier");
  await page.getByLabel(/город/i).fill("Tashkent");
  await page.getByLabel(/ИНН \/ Регистрационный номер/i).fill(uniqueTaxId());
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Yunusabad 8");
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3");

  // The disabled Next button is the actual protection here — a real disabled
  // native button never fires its click handler (not even with force:true),
  // and this step has no text input to Enter-submit through, so the
  // `submitted && !valid` inline error text this step also defines is
  // unreachable through any real user interaction. Not a functional bug (the
  // disabled button alone fully prevents an empty submission) but flagged —
  // dead validation-message code, and the same disabled-button-blocks-Enter
  // gap exists on every other toggle-only step (StepLogisticsSpecialization,
  // StepLogisticsGeography).
  await expect(page.getByTestId("wizard-next")).toBeDisabled();
});

test("laboratory step 2: invalid email blocks Next", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  await pickAccountType(page, "laboratory");
  await page.getByLabel(/название лаборатории/i).fill("OOO E2E Lab");
  await page.getByLabel(/город/i).fill("Tashkent");
  await page.getByLabel(/ИНН \/ Регистрационный номер/i).fill(uniqueTaxId());
  await page.getByLabel(/юридический адрес/i).first().fill("Tashkent, Mirzo Ulugbek 3");
  const email = page.getByLabel(/email/i);
  await email.fill("not-an-email");
  await email.blur();
  await expect(page.getByText("Укажите корректный email")).toBeVisible();
  await expect(page.getByTestId("wizard-next")).toBeDisabled();
});
