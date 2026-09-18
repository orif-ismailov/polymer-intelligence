import { expect, test, type Page } from "@playwright/test";

/**
 * The signing dialog must not blame the user for something that is not theirs
 * (IMEX-18).
 *
 * Three ways E-IMZO can be unusable, and they ask three different things of the
 * person looking at the screen:
 *
 *   1. nothing listening      → install it / start it
 *   2. certificate untrusted  → visit https://127.0.0.1:64443 once and accept it
 *   3. origin refused         → nothing; this deployment has no key for its domain
 *
 * The dialog used to answer «Установите E-IMZO» to all three. Cases 1 and 2 are
 * indistinguishable to a browser — both are WebSocket close 1006 with no detail,
 * because Chrome writes `net::ERR_CERT_AUTHORITY_INVALID` to the console and
 * exposes nothing to script. So the fix is not to guess between them but to STOP
 * guessing: one screen naming both causes, with the action for each. Case 3 IS
 * detectable (the module answers, status -1022) and gets its own screen —
 * telling someone to reinstall software over an API key their deployment was
 * never issued is the exact support load this ticket describes.
 *
 * Signs in as a SEEDED demo account rather than provisioning a fresh one: this
 * needs nothing but a company whose verification screen carries the button, and
 * `provisionAccount` is capped at 5 registrations per IP per hour, which no
 * suite that calls it in every spec can stay under.
 */

const LOGIN = process.env.PORTAL_DEMO_LOGIN ?? "zarafshan-owner";
const PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "demo-password-2026";
/** A company whose identity is NOT yet key-confirmed — otherwise the screen
 * shows `eimzo-confirmed` and the button this spec needs is gone. */
const COMPANY_ID = process.env.PORTAL_DEMO_COMPANY_ID ?? "85";

test.use({ locale: "ru-RU" });

/** Install a bridge reporting a specific unavailability, before the app boots. */
async function stubUnavailable(
  page: Page,
  reason: "unreachable" | "unauthorized_origin" | "silent",
): Promise<void> {
  await page.addInitScript((r) => {
    (window as unknown as { __EIMZO_BRIDGE__: unknown }).__EIMZO_BRIDGE__ = {
      probe: () => Promise.resolve(false),
      diagnose: () => Promise.resolve({ available: false, reason: r }),
      listCertificates: () => Promise.resolve([]),
      sign: () => Promise.reject(new Error("not reached")),
    };
  }, reason);
}

/**
 * Sign in by input type, not by label.
 *
 * `_registration.signIn` reaches for `getByLabel(/password|пароль|parol/i)`,
 * which matches the field AND the «Показать пароль» toggle beside it — a strict-
 * mode violation in every one of the three languages. Not this ticket's to fix,
 * but not something to inherit either.
 */
async function signInAsDemo(page: Page): Promise<void> {
  await page.goto("/cabinet/login");
  await page.locator('form input[type="text"], form input:not([type])').first().fill(LOGIN);
  await page.locator('form input[type="password"]').first().fill(PASSWORD);
  await page.getByRole("button", { name: /^(войти|sign in|kirish)$/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/cabinet/login"));
}

async function openSignDialog(page: Page): Promise<void> {
  await signInAsDemo(page);
  await page.goto(`/cabinet/companies/${COMPANY_ID}/verification`);
  await page.getByTestId("eimzo-open").click();
}

test("an unreachable module names BOTH causes, with the certificate remedy", async ({
  page,
}) => {
  await stubUnavailable(page, "unreachable");
  await openSignDialog(page);

  await expect(page.getByTestId("eimzo-module-missing")).toBeVisible({
    timeout: 20_000,
  });
  // Cause 1 keeps its download links…
  await expect(page.getByTestId("eimzo-cause-not-running")).toBeVisible();
  // …and cause 2 is what was missing entirely: the certificate, with a link that
  // actually produces Chrome's "proceed anyway" interstitial. A WebSocket never
  // shows one, which is why no user could discover this for themselves.
  await expect(page.getByTestId("eimzo-cause-cert")).toBeVisible();
  await expect(page.getByTestId("eimzo-trust-link")).toHaveAttribute(
    "href",
    "https://127.0.0.1:64443",
  );
});

test("a refused origin is shown as OUR misconfiguration, not a missing module", async ({
  page,
}) => {
  await stubUnavailable(page, "unauthorized_origin");
  await openSignDialog(page);

  // The error screen, NOT the install screen — the module is running fine, and
  // the domain key is ours to obtain.
  await expect(page.getByTestId("eimzo-error")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("eimzo-module-missing")).toHaveCount(0);
});
