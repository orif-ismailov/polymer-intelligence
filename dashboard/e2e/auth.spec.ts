import { test, expect } from "@playwright/test";
import { ADMIN, p, M } from "./helpers";

/**
 * Login-form behavior (anonymous project — no stored auth).
 * Covers REQ-roles staff auth at the UI boundary (the API's require_role is the real guard).
 */
test.describe("staff login", () => {
  test("rejects invalid credentials and stays on /login", async ({ page }) => {
    await page.goto(p("/login"));
    await page.locator('input[type="email"]').fill(ADMIN.email);
    await page.locator('input[type="password"]').fill("wrong-password");
    await page.getByRole("button", { name: M.login.signIn }).click();

    // Generic 401 surfaces as an inline error; user is not navigated away.
    await expect(page.getByRole("alert")).toBeVisible();
    // Stays on the (locale-prefixed) login page.
    await expect(page).toHaveURL(/\/login$/);
  });

  test("logs in with seeded admin and lands on the dashboard", async ({ page }) => {
    await page.goto(p("/login"));
    await page.locator('input[type="email"]').fill(ADMIN.email);
    await page.locator('input[type="password"]').fill(ADMIN.password);
    await page.getByRole("button", { name: M.login.signIn }).click();

    await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15_000 });
    // Protected chrome is now reachable.
    await page.goto(p("/requests"));
    await expect(page.getByText(M.requests.pageTitle).first()).toBeVisible();
  });
});
