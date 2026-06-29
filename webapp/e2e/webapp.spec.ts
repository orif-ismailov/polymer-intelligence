import { test, expect } from "@playwright/test";
import { openApp, openViaLaunchHash } from "./telegram";

/**
 * Telegram Web App buyer journeys (Vite app). A signed initData is passed via the
 * Telegram launch-params hash so the app authenticates against the live backend
 * exactly as it would inside Telegram.
 *
 * Covers REQ-webapp-auth (initData) + the request wizard (REQ-webapp-request) — the
 * buyer half of the §6.1.1 "request reaches the dashboard" acceptance flow.
 */

test("launches from the Telegram hash without blanking (HashRouter fix)", async ({ page }) => {
  // Telegram opens the Mini App with #tgWebAppData=... — HashRouter would treat that
  // as a route and render blank. The app must capture initData + clean the hash.
  await openViaLaunchHash(page);
  // Home (Главный экран) rendered (not blank); the launch hash was cleaned to "/".
  await expect(page.getByRole("button", { name: "Купить сырьё" })).toBeVisible();
  await expect(page).toHaveURL(/#\/$/);
  // initData was captured from the hash → an authed call works.
  await page.getByRole("button", { name: "Заявки" }).click();
  await expect(page.getByRole("heading", { name: /мои заявки/i })).toBeVisible();
  await expect(page.getByText(/не удалось загрузить/i)).toHaveCount(0);
});

test("My Requests loads for an authenticated buyer (initData auth)", async ({ page }) => {
  await openApp(page, "/requests");
  // Heading renders and the authed GET /webapp/requests resolved (no load-error banner).
  await expect(page.getByRole("heading", { name: /мои заявки/i })).toBeVisible();
  await expect(page.getByText(/не удалось загрузить/i)).toHaveCount(0);
});

test("submits a purchase request through the 4-step wizard", async ({ page }) => {
  await openApp(page, "/");

  // Home → buyer wizard
  await page.getByRole("button", { name: "Купить сырьё" }).click();
  await expect(page).toHaveURL(/\/request\/step\/1$/);

  // Step 1 — product (required) + grade + volume (required)
  await page.locator("#product_id").selectOption("1"); // Полипропилен (PP)
  await page.locator("#grade_text").fill("Grade A");
  await page.locator("#volume").fill("100");
  await page.getByRole("button", { name: "Далее" }).click();
  await expect(page).toHaveURL(/\/request\/step\/2$/);

  // Step 2 — delivery terms all optional
  await page.getByRole("button", { name: "Далее" }).click();
  await expect(page).toHaveURL(/\/request\/step\/3$/);

  // Step 3 — phone is the one required field before advancing
  await page.locator("#phone").fill("+998 90 123 45 67");
  await page.getByRole("button", { name: "Далее" }).click();
  await expect(page).toHaveURL(/\/request\/step\/4$/);

  // Step 4 — extras optional; "Отправить заявку" → confirm (auto-submits on mount)
  await page.getByRole("button", { name: "Отправить заявку" }).click();
  await expect(page).toHaveURL(/\/request\/confirm$/);

  // Success screen with the backend-assigned REQ number.
  await expect(page.getByRole("heading", { name: /заявка принята/i })).toBeVisible();
  const reqNumber = page.getByText(/^REQ-\d{4}-\d{2}-\d{2}-\d+$/);
  await expect(reqNumber).toBeVisible();

  // The new request shows up in My Requests.
  await page.getByRole("button", { name: "Мои заявки" }).click();
  await expect(page).toHaveURL(/\/requests$/);
  await expect(page.getByRole("heading", { name: /мои заявки/i })).toBeVisible();
  await expect(page.getByText(/^REQ-\d{4}-\d{2}-\d{2}-\d+$/).first()).toBeVisible();
});
