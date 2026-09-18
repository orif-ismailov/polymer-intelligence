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

  /**
   * The 401 branch must not lose what the person already typed (IMEX-17).
   *
   * `apiFetch` answers every 401 by navigating the whole document to /login,
   * which is right for an expired session and wrong for the login form itself —
   * the page was torn down before its own `catch` could render anything, so the
   * screen blinked, both fields emptied, and nothing said why. The email is the
   * half that was not wrong; retyping it on every attempt was the second
   * complaint in the ticket.
   */
  test("a refused password keeps the email and clears only the password", async ({
    page,
  }) => {
    await page.goto(p("/login"));
    await page.locator('input[type="email"]').fill(ADMIN.email);
    await page.locator('input[type="password"]').fill("wrong-password");
    await page.getByRole("button", { name: M.login.signIn }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.locator('input[type="email"]')).toHaveValue(ADMIN.email);
    await expect(page.locator('input[type="password"]')).toHaveValue("");
    // Announced to assistive tech as well as painted.
    await expect(page.locator('input[type="email"]')).toHaveAttribute(
      "aria-invalid",
      "true",
    );
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

  /**
   * A deep link survives the sign-in (IMEX-21).
   *
   * Both redirect paths used to send a bare `/login`, so a bookmark, a link in a
   * ticket, or a URL a colleague pasted cost the reader an extra navigation and
   * a manual hunt for the record they had been sent to.
   */
  test("signing in returns to the page that was asked for", async ({ page }) => {
    await page.goto(p("/deals"));
    await page.waitForURL(/\/login\?next=/, { timeout: 15_000 });

    await page.locator('input[type="email"]').fill(ADMIN.email);
    await page.locator('input[type="password"]').fill(ADMIN.password);
    await page.getByRole("button", { name: M.login.signIn }).click();

    await expect(page).toHaveURL(/\/deals$/, { timeout: 15_000 });
  });

  /**
   * An unsupported language prefix must not be STACKED under the default one.
   *
   * next-intl saw `/en/login` as an ordinary path and prefixed `ru` to it,
   * producing `/ru/en/login` — a route that cannot exist — so every `/en/…` link
   * anyone built or guessed ended on Next's bare 404 (IMEX-22).
   */
  for (const prefix of ["en", "xx"]) {
    test(`/${prefix}/login resolves to the default locale, not a nested prefix`, async ({
      page,
    }) => {
      const response = await page.goto(`/${prefix}/login`);
      expect(response?.status()).toBe(200);
      await expect(page).toHaveURL(/\/ru\/login$/);
      await expect(page.locator('input[type="email"]')).toBeVisible();
    });
  }
});
