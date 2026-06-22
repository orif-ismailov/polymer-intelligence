import { test, expect } from "@playwright/test";
import { ADMIN } from "./helpers";

/**
 * Login-form behavior (anonymous project — no stored auth).
 * Covers REQ-roles staff auth at the UI boundary (the API's require_role is the real guard).
 */
test.describe("staff login", () => {
  test("rejects invalid credentials and stays on /login", async ({ page }) => {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill(ADMIN.email);
    await page.locator('input[type="password"]').fill("wrong-password");
    await page.getByRole("button", { name: /sign in/i }).click();

    // Generic 401 surfaces as an inline error; user is not navigated away.
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("logs in with seeded admin and lands on the dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill(ADMIN.email);
    await page.locator('input[type="password"]').fill(ADMIN.password);
    await page.getByRole("button", { name: /sign in/i }).click();

    await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
    // Protected chrome is now reachable.
    await page.goto("/requests");
    await expect(page.getByText(/purchase requests/i).first()).toBeVisible();
  });
});
