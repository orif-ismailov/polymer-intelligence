import { test, expect } from "@playwright/test";
import { openApp } from "./telegram";

/**
 * TZ §6.1.1 acceptance flow, end to end across BOTH apps: a buyer submits a request
 * in the Telegram Web App and an analyst sees it in the internal dashboard.
 *
 * The two apps run in separate browser contexts (separate auth: the webapp uses a
 * signed Telegram initData; the dashboard uses staff JWT). A unique grade marker
 * links the submitted request to the row that surfaces in the dashboard.
 *
 * Note: this proves the data path (request reaches the dashboard). The strict
 * "≤10 s" SLA is a deploy-day measurement on real infra (see 06-ACCEPTANCE.md).
 */
const DASHBOARD_URL = `http://localhost:${process.env.E2E_DASH_PORT || 3138}`;
const ADMIN = {
  email: "admin@polymer.uz",
  password: "admin_dev_password_change_in_prod",
};

test("§6.1.1: a Web App purchase request appears in the dashboard", async ({ browser }) => {
  const marker = `E2E-${Date.now()}`;

  // ── 1) Buyer submits a request in the Telegram Web App ──────────────────────
  const webappCtx = await browser.newContext();
  const webappPage = await webappCtx.newPage();
  await openApp(webappPage, "/");
  await webappPage.getByRole("button", { name: "Купить сырьё" }).click();
  await webappPage.locator("#product_id").selectOption("1"); // PP
  await webappPage.locator("#grade_text").fill(marker);
  await webappPage.locator("#volume").fill("250");
  await webappPage.getByRole("button", { name: "Далее" }).click(); // step 1 → 2
  await webappPage.getByRole("button", { name: "Далее" }).click(); // step 2 → 3
  await webappPage.locator("#phone").fill("+998 90 123 45 67"); // step 3 requires phone
  await webappPage.getByRole("button", { name: "Далее" }).click(); // step 3 → 4
  await webappPage.getByRole("button", { name: "Отправить заявку" }).click();

  await expect(webappPage.getByRole("heading", { name: /заявка принята/i })).toBeVisible();
  const reqNumber = (
    await webappPage.getByText(/^REQ-\d{4}-\d{2}-\d{2}-\d+$/).first().textContent()
  )?.trim();
  expect(reqNumber).toMatch(/^REQ-\d{4}-\d{2}-\d{2}-\d+$/);

  // ── 2) Analyst sees it in the dashboard ─────────────────────────────────────
  const dashCtx = await browser.newContext({ baseURL: DASHBOARD_URL });
  const dashPage = await dashCtx.newPage();

  await dashPage.goto("/login");
  await dashPage.locator('input[type="email"]').fill(ADMIN.email);
  await dashPage.locator('input[type="password"]').fill(ADMIN.password);
  await dashPage.getByRole("button", { name: /sign in/i }).click();
  await dashPage.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15_000 });

  await dashPage.goto("/requests");
  // The buyer's request is present, identified by its unique grade marker.
  const markerCell = dashPage.getByText(marker).first();
  await expect(markerCell).toBeVisible();

  // Opening it shows a real request detail (REQ number + the same grade marker).
  await markerCell.click();
  await expect(dashPage).toHaveURL(/[?&]id=/);
  await expect(dashPage.getByRole("button", { name: /close detail panel/i })).toBeVisible();
  await expect(dashPage.getByText(/^REQ-\d{4}-\d{2}-\d{2}-\d+$/).first()).toBeVisible();
  await expect(dashPage.getByText(marker).first()).toBeVisible();

  await webappCtx.close();
  await dashCtx.close();
});
