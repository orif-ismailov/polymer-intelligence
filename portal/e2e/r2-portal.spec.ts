import { expect, test } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * R2 demo e2e: OTP login → register a company → announce a tender through the
 * 5-step wizard → see it in the tenders list with a status timeline → browse
 * the market, news and notification surfaces.
 *
 * Buying never requires a verified company, so this whole flow is self-serve (no
 * staff moderation). Requires a live migrated+seeded API on :8000 exposing the
 * dev-only the seeded demo logins. Not run in CI here (no live backend).
 */

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

test("buyer announces a tender and browses the R2 surfaces", async ({
  page,
}) => {
  await login(page, await provisionAccount(request));
  await registerCompany(page, uniqueTaxId());

  // ── Tender announced through the 5-step wizard ──────────────────────────────
  await page.goto("/cabinet/requests");
  // Two identical CTAs render on /requests (header + empty state) — take the header one.
  await page
    .getByRole("link", {
      name: /announce a tender|объявить тендер|tender e'lon qilish/i,
    })
    .first()
    .click();
  await page.waitForURL("**/cabinet/requests/new/**");

  // Step 1 — pick manual product entry
  await page.getByTestId("request-wizard-manual").click();
  await page.getByTestId("request-wizard-product-text").fill("HDPE film grade");
  await page.getByTestId("request-wizard-grade").fill("F0348");
  await page.getByTestId("request-wizard-next").click();

  // Step 2 — volume (defaults for the rest)
  await page.getByTestId("request-wizard-volume").fill("50");
  await page.getByTestId("request-wizard-next").click();

  // Step 3 — extra (optional)
  await page.getByTestId("request-wizard-next").click();

  // Step 4 — who sees the tender (defaults to verified suppliers only)
  await page.getByTestId("request-wizard-next").click();

  // Step 5 — publish
  await page.getByTestId("request-wizard-publish").click();

  // Lands on the published celebration, then the list still has the request.
  await page.waitForURL(/\/cabinet\/requests\/new\/done\/\d+$/);
  await expect(page.getByTestId("request-wizard-done")).toBeVisible();
  await page.getByTestId("request-wizard-done-list").click();
  await page.waitForURL("**/cabinet/requests");
  await expect(page.getByText(/REQ-|IMX-/).first()).toBeVisible();

  // ── Browse the other R2 surfaces (may be empty — headings must render) ──────
  await page.goto("/cabinet/market");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  await page.goto("/cabinet/news");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  await page.goto("/cabinet/notifications");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
