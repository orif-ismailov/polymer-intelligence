import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { login, registerCompany } from "./_registration";

/**
 * Role-based cabinet shape: the account type picked at registration decides
 * which features exist. The nav hides them, `RequireFeature` walks a direct
 * URL back to /cabinet, and the API answers 403 `role_not_allowed` — this spec
 * covers the first two (the API layer is pinned by
 * `backend/tests/test_portal_role_gates_api.py`).
 *
 * Requires a live migrated+seeded API on :8000 with the dev-only OTP peek —
 * the seeded laboratory/carrier phones are `seed_showcase`'s (same contract as
 * `lab-request.spec.ts` / `logistics-request.spec.ts`).
 */

const LAB_PHONE = process.env.PORTAL_LAB_PHONE ?? "+998901234530";
const CARRIER_PHONE = process.env.PORTAL_CARRIER_PHONE ?? "+998901234528";
const MANUFACTURER_PHONE = process.env.PORTAL_MANUFACTURER_PHONE ?? "+998901234501";

const OFFERS = /^(Предложения|Takliflar|Offers)$/;
const FAVORITES = /^(Избранное|Saralangan|Favorites)$/;
const INQUIRIES = /^(Запросы|So.rovlar|Inquiries)$/;
// The merged lab-hub entry (`nav.lab`) — one item where request-list and
// partner-lab-orders entries used to sit, still gated on `labOrdering`.
const LAB_ORDERING = /^(Лаборатория|Laboratoriya|Laboratory)$/;
const LOGISTICS_ORDERING = /^(Логистика: заявки|Logistika arizalari|Logistics requests)$/;

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

function navLink(page: Page, name: RegExp) {
  return page.getByRole("link", { name });
}

async function signIn(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.context().clearCookies();
  await login(page, request, phone);
  await page.goto("/cabinet");
}

test("a laboratory's cabinet has no trade features, and direct URLs walk home", async ({
  page,
  request,
}) => {
  await signIn(page, request, LAB_PHONE);

  // The seller/buyer entries are not merely hidden — they are not rendered at
  // all, in either nav instance (sidebar or drawer).
  await expect(navLink(page, OFFERS)).toHaveCount(0);
  await expect(navLink(page, FAVORITES)).toHaveCount(0);
  await expect(navLink(page, INQUIRIES)).toHaveCount(0);
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
  request,
}) => {
  await signIn(page, request, CARRIER_PHONE);

  await expect(navLink(page, OFFERS)).toHaveCount(0);
  await expect(navLink(page, LOGISTICS_ORDERING)).toHaveCount(0);
  await expect(navLink(page, LAB_ORDERING).first()).toBeVisible();

  await page.goto("/cabinet/logistics/requests");
  await page.waitForURL((url) => url.pathname === "/cabinet");
});

test("a distributor sees the trade features, before verification", async ({
  page,
  request,
}) => {
  await login(page, request, uniquePhone());
  await registerCompany(page, uniqueTaxId()); // default type: distributor
  await page.goto("/cabinet");

  // Declared roles shape the cabinet immediately — no staff action needed.
  await expect(navLink(page, OFFERS).first()).toBeVisible();
  await expect(navLink(page, FAVORITES).first()).toBeVisible();
  await expect(navLink(page, INQUIRIES).first()).toBeVisible();

  // /cabinet/offers is theirs (locked until verified, but not redirected).
  await page.goto("/cabinet/offers");
  await expect(page).toHaveURL(/\/cabinet\/offers$/);
});

test("a manufacturer keeps BOTH sides: sell features and buyer features", async ({
  page,
  request,
}) => {
  await signIn(page, request, MANUFACTURER_PHONE);

  // Sell side…
  await expect(navLink(page, OFFERS).first()).toBeVisible();
  // …and the buy side (raw-material procurement) at the same time.
  await expect(navLink(page, FAVORITES).first()).toBeVisible();
  await expect(navLink(page, INQUIRIES).first()).toBeVisible();
  await expect(navLink(page, LAB_ORDERING).first()).toBeVisible();
  await expect(navLink(page, LOGISTICS_ORDERING).first()).toBeVisible();

  // The supplier RFQ inbox is theirs too — no redirect.
  await page.goto("/cabinet/market/requests");
  await expect(page).toHaveURL(/\/cabinet\/market\/requests$/);
});

test("a buyer buys but never sells: no offers, no supplier inbox", async ({
  page,
  request,
}) => {
  await login(page, request, uniquePhone());
  await registerCompany(page, uniqueTaxId(), { type: "buyer" });
  await page.goto("/cabinet");

  // Buyer features are all there…
  await expect(navLink(page, FAVORITES).first()).toBeVisible();
  await expect(navLink(page, INQUIRIES).first()).toBeVisible();
  await expect(navLink(page, LAB_ORDERING).first()).toBeVisible();
  await expect(navLink(page, LOGISTICS_ORDERING).first()).toBeVisible();
  // …the seller surface is not.
  await expect(navLink(page, OFFERS)).toHaveCount(0);

  await page.goto("/cabinet/offers");
  await page.waitForURL((url) => url.pathname === "/cabinet");
  await page.goto("/cabinet/market/requests");
  await page.waitForURL((url) => url.pathname === "/cabinet");
});
