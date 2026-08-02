import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Signing in from the storefront returns you to the page you clicked from.
 *
 * `portal/CLAUDE.md` states this as a contract — «an anonymous CTA goes through
 * `/cabinet/login` with `state.from` set to the page it was clicked on, so
 * signing in from a listing returns you to *that listing*» — and it was broken
 * in two independent places at once, which is why nobody noticed the first one:
 *
 *  1. `OtpPage` gated the return path on `isCabinetPath`, so every storefront
 *     path was discarded in favour of `/cabinet`.
 *  2. `RedirectIfAuthed` re-renders the instant the verify writes a token and
 *     navigated to `/cabinet` unconditionally — so even with (1) fixed, the
 *     guard still overruled it and the observable behaviour did not change.
 *
 * Both now share `isSafeReturnPath`. A test that only covered (1) would have
 * passed against a still-broken app, so this drives the flow through the real
 * screens rather than asserting on the computed value.
 *
 * Requires a live migrated+seeded API on :8000 exposing the dev-only
 * `GET /portal/auth/otp/peek`.
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

/** Drive the two login screens, starting from wherever the caller already is. */
async function completeLogin(
  page: Page,
  request: APIRequestContext,
  phone: string,
): Promise<void> {
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();
  await page.waitForURL("**/cabinet/login/code");

  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  expect(res.ok()).toBeTruthy();
  const { code } = (await res.json()) as { code: string };

  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();
}

/** First company in a public directory, or null when the seed has none. */
async function anyCompanyId(
  request: APIRequestContext,
  slug: string,
): Promise<number | null> {
  const res = await request.get(`${API_BASE}/public/directories/${slug}`, {
    params: { limit: 1 },
  });
  if (!res.ok()) return null;
  const body = (await res.json()) as { items?: { id: number }[] };
  return body.items?.[0]?.id ?? null;
}

test("signing in from a company profile returns to that profile", async ({ page, request }) => {
  const companyId = await anyCompanyId(request, "logistics");
  test.skip(companyId === null, "no logistics company in this environment");

  const profile = `/logistics/${companyId}`;
  await page.goto(profile);

  // The anonymous CTA — the only control on the sheet before a session exists.
  await page.getByRole("link", { name: /contact|связаться|bog.lanish/i }).first().click();
  await page.waitForURL("**/cabinet/login");

  await completeLogin(page, request, uniquePhone());

  // The assertion the whole spec exists for: NOT /cabinet.
  await page.waitForURL((url) => url.pathname === profile);
  expect(new URL(page.url()).pathname).toBe(profile);
});

test("a login with no origin still lands on the cabinet home", async ({ page, request }) => {
  await page.goto("/cabinet/login");
  await completeLogin(page, request, uniquePhone());

  // No `state.from`, so the fallback applies. Onboarding is the correct landing
  // for a brand-new account with no company — what matters is that it is inside
  // the cabinet and not a stray public path.
  await page.waitForURL(/\/cabinet(\/|$)/);
  expect(new URL(page.url()).pathname.startsWith("/cabinet")).toBe(true);
});

/**
 * The retired cabinet addresses redirect for ANYONE.
 *
 * They are pure redirects to a page that is public, so they carry no guard.
 * That is load-bearing rather than incidental: declared deeper in the tree they
 * sat behind `RequireAuth` + `RequireCompany`, and an old bookmark opened by
 * someone with no company registered was answered with `/cabinet/onboarding` —
 * a signed-in dead end instead of the profile the link names. Asserting it
 * anonymously is what pins them outside the guards.
 */
for (const slug of ["logistics", "manufacturers"]) {
  test(`the retired /cabinet/${slug} address redirects anonymously`, async ({
    page,
    request,
  }) => {
    const companyId = await anyCompanyId(request, slug);
    test.skip(companyId === null, `no ${slug} company in this environment`);

    await page.goto(`/cabinet/${slug}/${companyId}`);
    // A `**/{slug}/{id}` glob would match `/cabinet/{slug}/{id}` too and resolve
    // before the redirect ever runs — match the exact pathname instead.
    await page.waitForURL((url) => url.pathname === `/${slug}/${companyId}`);
    expect(new URL(page.url()).pathname).toBe(`/${slug}/${companyId}`);
  });
}
