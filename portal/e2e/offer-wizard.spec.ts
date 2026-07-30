import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The add-product flow (`docs/new-design/product_creation.jpeg`), sheet by sheet:
 * «Информация → AI проверка → Наличие → Документы → Лабораторные данные →
 * Условия продажи → Дополнительная информация → Предварительный просмотр →
 * Публикация успешна».
 *
 * Requires a live migrated+seeded API on :8000 with the dev-only
 * `GET /portal/auth/otp/peek` endpoint AND a VERIFIED company for the account —
 * publishing is gated on verification, so the flow is unreachable without one.
 * Like `portal.spec.ts` this is a valid harness that CI does not run (no live
 * backend there).
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

const PDF = {
  mimeType: "application/pdf",
  buffer: Buffer.from("%PDF-1.4 test document"),
};

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

async function login(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();

  await page.waitForURL("**/login/code");
  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  expect(res.ok()).toBeTruthy();
  const { code } = (await res.json()) as { code: string };
  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();

  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

/** Walk sheet 1: name the product, then move on. */
async function fillBasics(page: Page, opts: { manual?: string } = {}): Promise<void> {
  await expect(page.getByTestId("offer-wizard-step-1")).toBeVisible();

  const select = page.getByTestId("offer-wizard-product");
  if (opts.manual) {
    await select.selectOption("other");
    await page.getByTestId("offer-wizard-product-text").fill(opts.manual);
  } else {
    // The first catalog row — index 0 is the disabled placeholder.
    await select.selectOption({ index: 1 });
  }
  await page.getByTestId("offer-wizard-next").click();
}

/** Sheet 2 gates «Далее» on the check settling, so wait for the verdict. */
async function passAiCheck(page: Page): Promise<void> {
  await expect(page.getByTestId("offer-wizard-step-2")).toBeVisible();
  await expect(page.getByTestId("offer-wizard-verdict")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("offer-wizard-next").click();
}

test.describe("add-product flow", () => {
  test.beforeEach(async ({ page, request }) => {
    await login(page, request, uniquePhone());
  });

  test("«Другое» reveals a manual name field, and the catalog choice hides it", async ({ page }) => {
    await page.goto("/offers/new/1");

    // An unverified account never reaches the sheets — publishing is gated, and
    // the locked screen says so instead of wasting seven sheets of typing.
    if (await page.getByText(/не верифицирована|not verified|tekshirilmagan/i).isVisible()) {
      test.skip(true, "account has no verified company; see the fixture note above");
    }

    const select = page.getByTestId("offer-wizard-product");
    await expect(page.getByTestId("offer-wizard-product-text")).toHaveCount(0);

    await select.selectOption("other");
    await expect(page.getByTestId("offer-wizard-product-text")).toBeVisible();

    await select.selectOption({ index: 1 });
    await expect(page.getByTestId("offer-wizard-product-text")).toHaveCount(0);
  });

  test("the first sheet will not advance without a product name", async ({ page }) => {
    await page.goto("/offers/new/1");
    if (await page.getByText(/не верифицирована|not verified|tekshirilmagan/i).isVisible()) {
      test.skip(true, "account has no verified company");
    }

    await page.getByTestId("offer-wizard-next").click();
    // Still on sheet 1, with the field flagged.
    await expect(page).toHaveURL(/\/offers\/new\/1/);
    await expect(page.getByTestId("offer-wizard-step-1")).toBeVisible();
  });

  test("a product walks all seven sheets and publishes", async ({ page }) => {
    await page.goto("/offers/new/1");
    if (await page.getByText(/не верифицирована|not verified|tekshirilmagan/i).isVisible()) {
      test.skip(true, "account has no verified company");
    }

    await fillBasics(page, { manual: `PP H030 GP ${uniqueTaxId()}` });
    await passAiCheck(page);

    // 3 — «Наличие / Под заказ»: in stock, so a quantity and a price are owed.
    await expect(page.getByTestId("offer-wizard-step-3")).toBeVisible();
    await page.getByTestId("offer-wizard-qty").fill("500");
    await page.getByTestId("offer-wizard-price").fill("1020");
    await page.getByTestId("offer-wizard-next").click();

    // 4 — «Документы»: SDS and TDS are required, COA is «если есть».
    await expect(page.getByTestId("offer-wizard-step-4")).toBeVisible();
    await page.getByTestId("offer-wizard-next").click();
    await expect(page.getByTestId("offer-wizard-step-4")).toBeVisible();

    const files = page.locator('input[type="file"]');
    await files.nth(0).setInputFiles({ name: "SDS_PP_H030GP.pdf", ...PDF });
    await files.nth(1).setInputFiles({ name: "TDS_PP_H030GP.pdf", ...PDF });
    await page.getByTestId("offer-wizard-next").click();

    // 5 — «Лабораторные данные»: «Нет паспорта» is a complete answer.
    await expect(page.getByTestId("offer-wizard-step-5")).toBeVisible();
    await page.getByTestId("offer-wizard-no-passport").click();
    await page.getByTestId("offer-wizard-next").click();

    // 6 — «Условия продажи».
    await expect(page.getByTestId("offer-wizard-step-6")).toBeVisible();
    await page.getByTestId("offer-wizard-next").click();

    // 7 — «Дополнительная информация».
    await expect(page.getByTestId("offer-wizard-step-7")).toBeVisible();
    await page.getByTestId("offer-wizard-description").fill("Полипропилен для литья под давлением.");
    await page.getByTestId("offer-wizard-next").click();

    // 8 — the preview, then the gold CTA.
    await expect(page.getByTestId("offer-wizard-step-preview")).toBeVisible();
    await expect(page.getByTestId("offer-wizard-preview-name")).toContainText("PP H030 GP");
    await page.getByTestId("offer-wizard-publish").click();

    await page.waitForURL(/\/offers\/new\/done\/\d+/, { timeout: 30_000 });
    await expect(page.getByTestId("offer-wizard-done")).toBeVisible();
    await expect(page.getByTestId("offer-wizard-public-id")).toContainText("#IMX-");
  });

  test("a lab passport is required once the seller says they have one", async ({ page }) => {
    await page.goto("/offers/new/5");
    if (await page.getByText(/не верифицирована|not verified|tekshirilmagan/i).isVisible()) {
      test.skip(true, "account has no verified company");
    }

    await expect(page.getByTestId("offer-wizard-step-5")).toBeVisible();
    await page.getByTestId("offer-wizard-has-passport").click();
    await page.getByTestId("offer-wizard-next").click();

    // Claiming a passport and attaching nothing is the sheet's only failure.
    await expect(page.getByTestId("offer-wizard-step-5")).toBeVisible();
    await expect(page.getByRole("alert")).toBeVisible();
  });
});
