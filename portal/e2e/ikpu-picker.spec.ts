import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
  type Route,
} from "@playwright/test";

/**
 * The ИКПУ picker on the offer wizard's «Дополнительная информация» sheet (P7.a W9).
 *
 * Everything here was found by driving the LIVE Didox test contour and is pinned
 * because a browser is the only place these three behaviours are visible:
 *
 * 1. **Search covers the company's own basket, not the tasnif directory.** Didox's
 *    partner API has no global search, so an empty result is the normal first
 *    experience and must offer the way forward.
 * 2. **Bind FIRST, then read back.** `productClasses/check/...` answers
 *    «танланган МХИКлар рўйхатида мавжуд эмас» for an unbound code, so the packages
 *    and the `origin` only exist after the bind — they can never be guessed.
 * 3. **The package select must survive picking.** It used to be derived from the
 *    search rows, which are cleared on pick, so a code with several packages could
 *    never have its package changed — on a field that reaches the tax authority.
 *
 * Auth is real (same harness as `offer-wizard.spec.ts` — live API on :8000 with the
 * dev-only OTP peek, and a verified company). The three ИКПУ routes are stubbed so
 * the assertions do not depend on what a shared test company happens to have bound,
 * and so the multi-package case is reachable at all: every polymer code in the live
 * directory carries exactly one package («тонна»).
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

const CODE = "03901001001000000";
const PACKAGES = [
  { code: "1486991", name: "тонна" },
  { code: "9999999", name: "килограмм" },
];
/** Didox's real shape: a name and packages, and `origin` ALWAYS null. */
const ROW = {
  class_code: CODE,
  name: "Полимер этилена (полиэтилен)",
  origin_id: null,
  origin_name: null,
  use_package: true,
  packages: PACKAGES,
};

/**
 * Reaching the sheet at all needs an account with a VERIFIED company, which a
 * freshly minted phone never has — it lands on onboarding instead. Point
 * `PORTAL_E2E_PHONE` at such an account to run these; without it they skip, the
 * same bargain `offer-wizard.spec.ts` makes. OTP is throttled per phone AND per
 * IP, so between local runs clear it:
 * `docker exec pi-redis redis-cli --scan --pattern 'otp:*' | xargs -r docker exec -i pi-redis redis-cli DEL`
 */
const PHONE = process.env.PORTAL_E2E_PHONE ?? "";

async function login(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.goto("/cabinet/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();

  await page.waitForURL("**/cabinet/login/code");
  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  expect(res.ok()).toBeTruthy();
  const { code } = (await res.json()) as { code: string };
  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();

  await page.waitForURL((url) => !url.pathname.startsWith("/cabinet/login"));
}

/** The basket the stubbed Didox answers from — empty until `bind` is called. */
function stubIkpu(page: Page, opts: { bound?: boolean } = {}): { binds: string[] } {
  const binds: string[] = [];
  let bound = opts.bound ?? false;

  const json = (route: Route, body: unknown) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

  void page.route("**/portal/ikpu/search**", (route) => {
    const term = new URL(route.request().url()).searchParams.get("q") ?? "";
    const hit = bound && (CODE.includes(term) || /полиэтилен|полимер/i.test(term));
    return json(route, hit ? [ROW] : []);
  });
  void page.route(`**/portal/companies/*/ikpu/*/bind`, (route) => {
    binds.push(route.request().url());
    bound = true;
    return json(route, null);
  });
  void page.route(`**/portal/companies/*/ikpu/*/packages`, (route) => json(route, PACKAGES));

  return { binds };
}

async function openPickerSheet(page: Page): Promise<boolean> {
  await page.goto("/cabinet/offers/new/7");
  // The sheet is unreachable without a verified company — the wizard renders a
  // locked screen, or `RequireCompany` diverts to onboarding entirely.
  try {
    await page.getByTestId("ikpu-query").waitFor({ state: "visible", timeout: 5_000 });
    return true;
  } catch {
    return false;
  }
}

test.describe("ИКПУ picker", () => {
  test.skip(!PHONE, "set PORTAL_E2E_PHONE to an account with a verified company");

  /**
   * Log in ONCE and hand the refresh cookie to each test.
   *
   * OTP is throttled per phone AND per IP, so a `beforeEach` login fails every
   * test after the first. The access token lives in memory only, so the cookie is
   * the whole session — the app re-mints from it during its boot-time refresh.
   */
  let cookies: Awaited<ReturnType<BrowserContext["cookies"]>> = [];

  test.beforeAll(async ({ browser }) => {
    if (!PHONE) return;
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page, context.request, PHONE);
    cookies = await context.cookies();
    await context.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.context().addCookies(cookies);
  });

  test("an empty result offers to add the code instead of dead-ending", async ({ page }) => {
    stubIkpu(page);
    test.skip(!(await openPickerSheet(page)), "account has no verified company");

    // A word the basket cannot contain — the normal first search.
    await page.getByTestId("ikpu-query").fill("полиэтилен");
    await page.getByTestId("ikpu-search").click();

    await expect(page.getByTestId("ikpu-empty")).toBeVisible();
    // A word is not a code, so there is nothing to add yet — and the button says why.
    await expect(page.getByTestId("ikpu-add")).toBeDisabled();

    await page.getByTestId("ikpu-query").fill(CODE);
    await expect(page.getByTestId("ikpu-add")).toBeEnabled();
  });

  test("adding a code binds it, then reads the row BACK from Didox", async ({ page }) => {
    const { binds } = stubIkpu(page);
    test.skip(!(await openPickerSheet(page)), "account has no verified company");

    await page.getByTestId("ikpu-query").fill(CODE);
    await page.getByTestId("ikpu-search").click();
    await page.getByTestId("ikpu-add").click();

    expect(binds).toHaveLength(1);
    expect(binds[0]).toContain(CODE);

    // The NAME comes from the read-back, never from what the seller typed.
    const chosen = page.getByTestId("ikpu-chosen");
    await expect(chosen).toContainText(CODE);
    await expect(chosen).toContainText("Полимер этилена");
    await expect(chosen).toContainText("тонна");
  });

  test("the package select survives picking, and the choice sticks across a remount", async ({
    page,
  }) => {
    stubIkpu(page, { bound: true });
    test.skip(!(await openPickerSheet(page)), "account has no verified company");

    await page.getByTestId("ikpu-query").fill(CODE);
    await page.getByTestId("ikpu-search").click();
    await page.getByTestId("ikpu-results").getByRole("button").first().click();

    // The regression: picking used to clear the rows the select was derived from.
    const select = page.getByTestId("ikpu-chosen").getByRole("combobox").first();
    await expect(select).toBeVisible();
    await select.selectOption("9999999");
    await expect(page.getByTestId("ikpu-chosen")).toContainText("килограмм");

    // Origin is the seller's own answer — Didox returns null for every row — and
    // the offer cannot be published until it is given.
    await expect(page.getByTestId("ikpu-origin-missing")).toBeVisible();
    await page.getByTestId("ikpu-origin").selectOption("1");
    await expect(page.getByTestId("ikpu-origin-missing")).toHaveCount(0);

    // Walking on and back must not lose the package. (A RELOAD would — the wizard
    // draft lives in memory — so the way a chosen code comes back without a search
    // behind it is the EDIT flow, `/cabinet/offers/:id/edit/7`, which hydrates from
    // the offer and needs the packages re-fetched to stay changeable.)
    await page.getByTestId("offer-wizard-next").click();
    await expect(page).toHaveURL(/\/cabinet\/offers\/new\/8/);
    await page.goBack();
    await expect(page).toHaveURL(/\/cabinet\/offers\/new\/7/);

    await expect(page.getByTestId("ikpu-chosen")).toContainText("килограмм");
    await expect(page.getByTestId("ikpu-origin")).toHaveValue("1");
  });
});
