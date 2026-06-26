import { test, expect } from "@playwright/test";
import { p, M } from "./helpers";

/**
 * Authenticated dashboard journeys (chromium project — reuses the admin storageState;
 * the layout silently refreshes the access token from the refresh cookie on load).
 *
 * Covers the flagship Purchase Requests master-detail (REQ-purchase-requests) and a
 * navigation smoke across every guarded section (REQ-dashboard). Text is asserted
 * against the default-locale (ru) message catalog `M`, since the dashboard renders
 * Russian by default under /[locale]/.
 */

test("home overview is wired to real data (no placeholders)", async ({ page }) => {
  await page.goto(p("/"));
  await expect(page.getByRole("heading", { name: M.home.title, exact: true })).toBeVisible();

  // All the old "wired in Plan 04-XX" / "available after Phase 5" stubs are gone
  // (these English placeholder strings no longer exist in any locale).
  await expect(page.getByText(/wired in plan/i)).toHaveCount(0);
  await expect(page.getByText(/available after phase 5/i)).toHaveCount(0);

  // The three formerly-placeholder panels now render real seed data.
  await expect(page.getByRole("heading", { name: M.home.topBuyerRequests })).toBeVisible();
  await expect(page.getByText(/^REQ-DEMO-\d+/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: M.home.topSellerOffers })).toBeVisible();
  await expect(page.getByRole("heading", { name: M.home.aiMarketSignals })).toBeVisible();
  await expect(page.getByText(/^HOT$/).first()).toBeVisible(); // seeded HOT-classified signal
});

test("flagship: Purchase Requests master-detail opens a request", async ({ page }) => {
  await page.goto(p("/requests"));

  // Master: header + the table populated from the API. The table identifies rows
  // by data, not by a visible request-number column; target a data row by its
  // price cell, which always renders the locale-independent "…/MT" unit suffix.
  await expect(page.getByRole("heading", { name: M.requests.pageTitle })).toBeVisible();
  const firstRow = page.getByRole("row").filter({ hasText: "MT" }).first();
  await expect(firstRow).toBeVisible();

  // Detail: clicking the row sets ?id= and mounts RequestDetailPanel. Rows sort
  // newest-first, so the first row is the seed REQ-DEMO-001 — the panel renders
  // its number, proving the master→detail data linkage end to end.
  await firstRow.click();
  await expect(page).toHaveURL(/[?&]id=/);
  await expect(page.getByRole("button", { name: M.requests.closeDetailPanel })).toBeVisible();
  await expect(page.getByText(M.requests.fieldTargetPrice).first()).toBeVisible();
  await expect(page.getByText(/^REQ-DEMO-\d+$/).first()).toBeVisible();
});

const SECTIONS: ReadonlyArray<readonly [string, string]> = [
  ["/", M.home.title],
  ["/requests", M.requests.pageTitle],
  ["/signals", M.signals.title],
  ["/prices", M.prices.title],
  ["/sources", M.sources.title],
  ["/alerts", M.alerts.pageTitle],
  ["/offers", M.offers.title],
];

for (const [path, heading] of SECTIONS) {
  test(`navigation: ${path} renders for an authenticated admin`, async ({ page }) => {
    await page.goto(p(path));
    // Did not bounce to /login (auth held via the refresh cookie).
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
  });
}
