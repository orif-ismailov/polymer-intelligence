import { expect, test, type Page } from "@playwright/test";

import { login, registerCompany } from "./_registration";

/**
 * Role-based cabinet shape: the account type picked at registration decides
 * which features exist. The nav hides them, `RequireFeature` walks a direct
 * URL back to /cabinet, and the API answers 403 `role_not_allowed` — this spec
 * covers the first two (the API layer is pinned by
 * `backend/tests/test_portal_role_gates_api.py`).
 *
 * Requires a live migrated+seeded API on :8000 with the seeded demo
 * logins from `seed_showcase` (same contract as
 * `lab-request.spec.ts` / `logistics-request.spec.ts`).
 */

const DEMO_PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "demo-password-2026";
const LAB = {
  login: process.env.PORTAL_LAB_LOGIN ?? "cptl_lab-owner",
  password: DEMO_PASSWORD,
};
const CARRIER = {
  login: process.env.PORTAL_CARRIER_LOGIN ?? "trans_asia-owner",
  password: DEMO_PASSWORD,
};
const MANUFACTURER = {
  login: process.env.PORTAL_MANUFACTURER_LOGIN ?? "shurtan-owner",
  password: DEMO_PASSWORD,
};

const OFFERS = /^(Предложения|Takliflar|Offers)$/;
const FAVORITES = /^(Избранное|Saralangan|Favorites)$/;
const INQUIRIES = /^(Запросы|So.rovlar|Inquiries)$/;
// The supplier's quoting inbox — buyer tenders from OTHER companies. It had a
// route and a role gate but no nav entry at all until this spec asked for one.
const OPEN_TENDERS = /^(Открытые тендеры|Ochiq tenderlar|Open tenders)$/;
// The merged lab-hub entry (`nav.lab`) — one item where request-list and
// partner-lab-orders entries used to sit, still gated on `labOrdering`.
const LAB_ORDERING = /^(Лаборатория|Laboratoriya|Laboratory)$/;
const LOGISTICS_ORDERING =
  /^(Логистика: заявки|Logistika arizalari|Logistics requests)$/;

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

function navLink(page: Page, name: RegExp) {
  return page.getByRole("link", { name });
}

async function signInAs(page: Page, creds: Credentials): Promise<void> {
  await page.context().clearCookies();
  await login(page, creds);
  await page.goto("/cabinet");
}

test("a laboratory's cabinet has no trade features, and direct URLs walk home", async ({
  page,
}) => {
  await signInAs(page, LAB);

  // The seller/buyer entries are not merely hidden — they are not rendered at
  // all, in either nav instance (sidebar or drawer).
  await expect(navLink(page, OFFERS)).toHaveCount(0);
  await expect(navLink(page, FAVORITES)).toHaveCount(0);
  await expect(navLink(page, INQUIRIES)).toHaveCount(0);
  await expect(navLink(page, OPEN_TENDERS)).toHaveCount(0);
  // Its own service side is closed too…
  await expect(navLink(page, LAB_ORDERING)).toHaveCount(0);
  // …but the OTHER service stays: a lab ships samples (cross-service).
  await expect(navLink(page, LOGISTICS_ORDERING).first()).toBeVisible();

  // A direct URL is a silent redirect to the cabinet home, not an error page.
  await page.goto("/cabinet/offers");
  await page.waitForURL((url) => url.pathname === "/cabinet");
  await page.goto("/cabinet/market/favorites");
  await page.waitForURL((url) => url.pathname === "/cabinet");
});

test("a carrier keeps cross-service lab ordering but loses its own buyer page", async ({
  page,
}) => {
  await signInAs(page, CARRIER);

  await expect(navLink(page, OFFERS)).toHaveCount(0);
  await expect(navLink(page, OPEN_TENDERS)).toHaveCount(0);
  await expect(navLink(page, LOGISTICS_ORDERING)).toHaveCount(0);
  await expect(navLink(page, LAB_ORDERING).first()).toBeVisible();

  await page.goto("/cabinet/logistics/requests");
  await page.waitForURL((url) => url.pathname === "/cabinet");
});

test("a distributor sees the trade features, before verification", async ({
  page,
}) => {
  await login(page, await provisionAccount(request));
  await registerCompany(page, uniqueTaxId()); // default type: distributor
  await page.goto("/cabinet");

  // Declared roles shape the cabinet immediately — no staff action needed.
  await expect(navLink(page, OFFERS).first()).toBeVisible();
  await expect(navLink(page, FAVORITES).first()).toBeVisible();
  await expect(navLink(page, INQUIRIES).first()).toBeVisible();
  await expect(navLink(page, OPEN_TENDERS).first()).toBeVisible();

  // /cabinet/offers is theirs (locked until verified, but not redirected).
  await page.goto("/cabinet/offers");
  await expect(page).toHaveURL(/\/cabinet\/offers$/);
});

test("a manufacturer keeps BOTH sides: sell features and buyer features", async ({
  page,
}) => {
  await signInAs(page, MANUFACTURER);

  // Sell side…
  await expect(navLink(page, OFFERS).first()).toBeVisible();
  // …and the buy side (raw-material procurement) at the same time.
  await expect(navLink(page, FAVORITES).first()).toBeVisible();
  await expect(navLink(page, INQUIRIES).first()).toBeVisible();
  await expect(navLink(page, LAB_ORDERING).first()).toBeVisible();
  await expect(navLink(page, LOGISTICS_ORDERING).first()).toBeVisible();

  // The supplier RFQ inbox is theirs too — reachable from the nav, no redirect.
  await expect(navLink(page, OPEN_TENDERS).first()).toBeVisible();
  await page.goto("/cabinet/market/requests");
  await expect(page).toHaveURL(/\/cabinet\/market\/requests$/);
});

test("a buyer buys but never sells: no offers, no supplier inbox", async ({
  page,
}) => {
  await login(page, await provisionAccount(request));
  await registerCompany(page, uniqueTaxId(), { type: "buyer" });
  await page.goto("/cabinet");

  // Buyer features are all there…
  await expect(navLink(page, FAVORITES).first()).toBeVisible();
  await expect(navLink(page, INQUIRIES).first()).toBeVisible();
  await expect(navLink(page, LAB_ORDERING).first()).toBeVisible();
  await expect(navLink(page, LOGISTICS_ORDERING).first()).toBeVisible();
  // …the seller surface is not.
  await expect(navLink(page, OFFERS)).toHaveCount(0);
  await expect(navLink(page, OPEN_TENDERS)).toHaveCount(0);

  await page.goto("/cabinet/offers");
  await page.waitForURL((url) => url.pathname === "/cabinet");
  await page.goto("/cabinet/market/requests");
  await page.waitForURL((url) => url.pathname === "/cabinet");
});
