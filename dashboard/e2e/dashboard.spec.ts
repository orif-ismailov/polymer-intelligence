import { test, expect } from "@playwright/test";

/**
 * Authenticated dashboard journeys (chromium project — reuses the admin storageState;
 * the layout silently refreshes the access token from the refresh cookie on load).
 *
 * Covers the flagship Purchase Requests master-detail (REQ-purchase-requests) and a
 * navigation smoke across every guarded section (REQ-dashboard).
 */

test("home overview is wired to real data (no placeholders)", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /^dashboard$/i })).toBeVisible();

  // All the old "wired in Plan 04-XX" / "available after Phase 5" stubs are gone.
  await expect(page.getByText(/wired in plan/i)).toHaveCount(0);
  await expect(page.getByText(/available after phase 5/i)).toHaveCount(0);

  // The three formerly-placeholder panels now render real seed data.
  await expect(page.getByRole("heading", { name: /top buyer requests/i })).toBeVisible();
  await expect(page.getByText(/^REQ-DEMO-\d+/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /top seller offers/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /ai market signals/i })).toBeVisible();
  await expect(page.getByText(/^HOT$/).first()).toBeVisible(); // seeded HOT-classified signal
});

test("flagship: Purchase Requests master-detail opens a request", async ({ page }) => {
  await page.goto("/requests");

  // Master: header + the table populated from the API. The table identifies rows
  // by data (Time/Product/Volume/…), not by a visible request-number column, so
  // assert the result count and target a data row by its volume cell ("… MT").
  await expect(page.getByRole("heading", { name: /purchase requests/i })).toBeVisible();
  await expect(page.getByText(/\d+ results/i)).toBeVisible();
  const firstRow = page.getByRole("row").filter({ hasText: "MT" }).first();
  await expect(firstRow).toBeVisible();

  // Detail: clicking the row sets ?id= and mounts RequestDetailPanel. Rows sort
  // newest-first, so the first row is the seed REQ-DEMO-001 — the panel renders
  // its number, proving the master→detail data linkage end to end.
  await firstRow.click();
  await expect(page).toHaveURL(/[?&]id=/);
  await expect(page.getByRole("button", { name: /close detail panel/i })).toBeVisible();
  await expect(page.getByText(/target price/i).first()).toBeVisible();
  await expect(page.getByText(/^REQ-DEMO-\d+$/).first()).toBeVisible();
});

const SECTIONS: ReadonlyArray<readonly [string, RegExp]> = [
  ["/", /dashboard/i],
  ["/requests", /purchase requests/i],
  ["/signals", /live feed/i],
  ["/prices", /price trends/i],
  ["/sources", /sources/i],
  ["/alerts", /alerts/i],
  ["/offers", /seller offers/i],
];

for (const [path, heading] of SECTIONS) {
  test(`navigation: ${path} renders for an authenticated admin`, async ({ page }) => {
    await page.goto(path);
    // Did not bounce to /login (auth held via the refresh cookie).
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
  });
}
