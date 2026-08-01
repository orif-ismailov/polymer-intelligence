import { expect, test, type APIRequestContext } from "@playwright/test";

import { login, registerCompany } from "./_registration";

/**
 * The storefront is open to everyone — signing in must not close it.
 *
 * The portal used to wrap every public route in a guard that moved any visitor
 * with a session to the `/cabinet` twin of whatever they opened, so the moment
 * you logged in the marketplace, a company's public profile and every listing
 * URL a colleague had sent you became unreachable. What is behind the login is
 * the ability to ACT, not the ability to READ, and this spec is what holds that
 * line: it asserts the URL does not move.
 *
 * Requires a live migrated+seeded API on :8000 exposing the dev-only
 * `GET /portal/auth/otp/peek`. Not run in CI here (no live backend).
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

/** Every public path that has a `/cabinet` twin it must NOT be pulled into. */
const PUBLIC_PATHS = ["/", "/market", "/news", "/prices", "/manufacturers"];

const SIGN_IN = /^(sign in|войти|kirish)$/i;
const CABINET = /^(cabinet|кабинет|kabinet)$/i;
const MARKETPLACE = /^(marketplace|маркетплейс|marketpleys)$/i;

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

/** First published listing, or null when the marketplace is empty. */
async function anyPublicOfferId(request: APIRequestContext): Promise<number | null> {
  const res = await request.get(`${API_BASE}/public/offers`, { params: { limit: 1 } });
  if (!res.ok()) return null;
  const body = (await res.json()) as { items?: { id: number }[] };
  return body.items?.[0]?.id ?? null;
}

test("anonymous visitors get the storefront and its two auth CTAs", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: SIGN_IN }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: CABINET })).toHaveCount(0);
});

/*
 * The other half of "one address per listing": a listing reads in full without a
 * session, and carries none of the acting surface.
 *
 * This is the cacheability contract as much as an auth one — `/market/:id` is
 * served with `s-maxage=60` precisely because nothing in that HTML varies by
 * visitor, so an action leaking into the anonymous render would be served to
 * everyone from the edge.
 */
test("an anonymous visitor reads a listing but gets no acting surface", async ({
  page,
  request,
}) => {
  const offerId = await anyPublicOfferId(request);
  test.skip(offerId === null, "no published listing to read");

  await page.goto(`/market/${offerId}`);

  await expect(page.getByTestId("product-detail-hero")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(
    page.getByRole("link", { name: /sign in to contact|войти, чтобы связаться/i }),
  ).toBeVisible();

  for (const testId of [
    "product-detail-rfq",
    "product-detail-favorite",
    "product-detail-action-bar",
    "inquiry-submit",
  ]) {
    await expect(page.getByTestId(testId)).toHaveCount(0);
  }
});

/*
 * One signed-in session for the whole authed story: registering a company is
 * ~15 s of wizard, and the suite shares one OTP rate-limit bucket per IP.
 */
test("a signed-in visitor keeps the storefront", async ({ page, request }) => {
  const offerId = await anyPublicOfferId(request);

  // A company, not just a session: `RequireCompany` sends an account with none
  // to `/cabinet/onboarding`, which renders outside `AppShell` and so has no
  // sidebar for the return trip below.
  await login(page, request, uniquePhone());
  await registerCompany(page, uniqueTaxId());

  for (const path of PUBLIC_PATHS) {
    await page.goto(path);
    // The assertion is the URL — but read it only once the header proves the
    // session is live, since the guard this replaces fired after the boot-time
    // refresh resolved, not on navigation.
    await expect(page.getByRole("link", { name: CABINET }).first()).toBeVisible();
    expect(new URL(page.url()).pathname).toBe(path);
    await expect(page.getByRole("link", { name: SIGN_IN })).toHaveCount(0);
  }

  // A listing has ONE address. Signing in does not move the visitor to a cabinet
  // twin — that twin is gone — it grows the acting controls in place, mounted
  // after hydration so the cached HTML stays the same for everyone.
  if (offerId !== null) {
    await page.goto(`/market/${offerId}`);
    await expect(page.getByTestId("product-detail-rfq")).toBeVisible();
    expect(new URL(page.url()).pathname).toBe(`/market/${offerId}`);
    await expect(page.getByTestId("product-detail-favorite")).toBeVisible();
    await expect(page.getByTestId("product-detail-action-bar")).toBeVisible();
    // The sign-in prompt is what the actions replaced.
    await expect(
      page.getByRole("link", { name: /sign in to contact|войти, чтобы связаться/i }),
    ).toHaveCount(0);
  }

  // ...and the two ways back out: the sidebar link and the brand lockup, which
  // points at the public home from every surface that draws it.
  await page.goto("/cabinet");
  await page.getByRole("link", { name: MARKETPLACE }).click();
  await page.waitForURL((url) => url.pathname === "/");

  await page.goto("/cabinet/offers");
  await page.getByRole("link", { name: "IMEX AI" }).first().click();
  await page.waitForURL((url) => url.pathname === "/");
});

test("the logo leads to the public home from the login screen too", async ({ page }) => {
  await page.goto("/cabinet/login");
  await page.getByRole("link", { name: "IMEX AI" }).first().click();
  await page.waitForURL((url) => url.pathname === "/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
