import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Regression: a company-wizard draft saved by an OLDER build must not crash the
 * wizard.
 *
 * The draft is persisted to localStorage, and zustand's default `merge` is
 * shallow — a stored `identity` replaced the default object wholesale, so every
 * field added afterwards rehydrated as `undefined`. Opening the wizard with a
 * pre-manufacturer-flow draft then threw `Cannot read properties of undefined
 * (reading 'trim')` out of `isManufacturerIdentityValid` and took the entire
 * route down to the router's error boundary.
 *
 * The drafts that trigger it are real ones sitting in real browsers, so the
 * fixtures below are the literal shapes those builds wrote — deliberately typed
 * as the bare JSON they are, not as `WizardIdentity`, because the whole point is
 * that they no longer satisfy it.
 *
 * Requires a live migrated+seeded API on :8000 exposing the dev-only
 * `GET /portal/auth/otp/peek`.
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";
const PERSIST_KEY = "imex.company-wizard.draft";

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

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

/**
 * Uncaught `TypeError`s only.
 *
 * Cabinet routes are shell-only from the SSR server, so React reports a
 * hydration mismatch and re-renders on the client for every one of them. That is
 * a separate defect with its own noise; asserting "no page errors at all" here
 * would tie this regression to it and stay red for unrelated reasons. A reading
 * of `undefined` is a `TypeError`, which the hydration reports are not.
 */
function typeErrorsFrom(errors: Array<{ name: string; message: string }>): string[] {
  return errors.filter((e) => e.name === "TypeError").map((e) => e.message);
}

/** Write a raw persisted draft, then reload so the store rehydrates from it. */
async function seedDraft(page: Page, state: Record<string, unknown>): Promise<void> {
  await page.evaluate(
    ([key, payload]) => window.localStorage.setItem(key as string, payload as string),
    [PERSIST_KEY, JSON.stringify({ state, version: 0 })] as const,
  );
}

/**
 * The shape written before the manufacturer/logistics/laboratory flow existed:
 * `identity` has no `actual_address` or `registration_number`, and there are no
 * `logistics`/`laboratory` slices at all.
 */
const LEGACY_IDENTITY = {
  jurisdiction: "UZ",
  tax_id: "123456789",
  legal_name: "OOO Legacy Draft",
  short_name: "",
  legal_form: "ООО",
  legal_address: "Ташкент, Амир Темур 1",
  director_name: "",
  registration_date: "2020-01-01",
};

const LEGACY_BANK = {
  enabled: false,
  bank_mfo: "",
  account_number: "",
  bank_name: "",
  currency: "UZS",
};

test.describe("company-wizard draft rehydration", () => {
  test("a pre-typed-flow draft opens the wizard instead of crashing it", async ({
    page,
    request,
  }) => {
    const errors: Array<{ name: string; message: string }> = [];
    page.on("pageerror", (err) => errors.push({ name: err.name, message: err.message }));

    await login(page, request, uniquePhone());

    // `manufacturer` is the branch that reads the two fields the old draft lacks.
    await seedDraft(page, {
      accountType: "manufacturer",
      identity: LEGACY_IDENTITY,
      bank: LEGACY_BANK,
      companyId: null,
      identityLocked: false,
    });

    await page.goto("/cabinet/companies/new/1");

    await expect(page.getByTestId("account-type-manufacturer")).toBeVisible();

    // What survived matters as much as not crashing. Step 2 is reachable (the
    // draft satisfies step 1), and it renders both halves of the merge: the
    // legal name the user typed, and the field that build never had — as an
    // empty controlled input rather than `undefined`.
    await page.goto("/cabinet/companies/new/2");

    await expect(
      page.getByLabel(/legal name of the factory|название завода|zavodning to.liq yuridik nomi/i),
    ).toHaveValue("OOO Legacy Draft");
    await expect(
      page.getByLabel(/actual factory address|фактический адрес завода|zavodning amaldagi manzili/i),
    ).toHaveValue("");

    expect(typeErrorsFrom(errors)).toEqual([]);
  });

  /**
   * A slice that is PRESENT but half-populated, which is what every future field
   * addition produces. It matters that this is a separate case: an absent
   * `logistics`/`laboratory` is already covered, because `isIdentityValidForType`
   * defaults an `undefined` argument to the empty profile. A `{}` is not
   * `undefined`, so that default never fires and the validator reads straight
   * through to `.city.trim()`.
   */
  const PARTIAL_SLICES = [
    { accountType: "logistics", slice: "logistics", value: {} },
    { accountType: "laboratory", slice: "laboratory", value: { city: "Ташкент" } },
  ] as const;

  for (const { accountType, slice, value } of PARTIAL_SLICES) {
    test(`the ${accountType} branch survives a half-populated ${slice} slice`, async ({
      page,
      request,
    }) => {
      const errors: Array<{ name: string; message: string }> = [];
      page.on("pageerror", (err) => errors.push({ name: err.name, message: err.message }));

      await login(page, request, uniquePhone());

      await seedDraft(page, {
        accountType,
        identity: LEGACY_IDENTITY,
        bank: LEGACY_BANK,
        [slice]: value,
        companyId: null,
        identityLocked: false,
      });

      await page.goto("/cabinet/companies/new/1");

      await expect(page.getByTestId(`account-type-${accountType}`)).toBeVisible();
      expect(typeErrorsFrom(errors)).toEqual([]);
    });
  }
});
