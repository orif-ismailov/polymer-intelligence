import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * R3 Stage A e2e: E-IMZO onboarding with a STUBBED CAPIWS bridge (CI has no local
 * E-IMZO module). The browser bridge is injected on `window.__EIMZO_BRIDGE__`; the
 * backend must run with EIMZO_STUB=true so its gateway verifies the synthetic
 * PKCS#7 the stub produces. Covers the happy path (sign → auto-approve/confirm)
 * and the module-missing path.
 *
 * Prerequisites: live backend on :8000 with DEBUG=true + EIMZO_STUB=true, and
 * OTP_MAX_SENDS_PER_DAY raised (the daily cap is per client IP as well as per
 * phone, so the default 5 blocks repeated runs from one machine).
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

async function readOtp(request: APIRequestContext, phone: string): Promise<string> {
  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { code: string };
  return body.code;
}

async function login(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();
  await page.waitForURL("**/login/code");
  const code = await readOtp(request, phone);
  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

/** Inject a working stub CAPIWS bridge whose cert INN matches `taxId`. */
async function stubEimzo(page: Page, taxId: string, opts: { available: boolean }): Promise<void> {
  await page.addInitScript(
    ([tax, available]) => {
      (window as unknown as { __EIMZO_BRIDGE__: unknown }).__EIMZO_BRIDGE__ = {
        probe: async () => available,
        listCertificates: async () => [
          { id: "k1", subjectName: "OOO Polymer Trade", tin: tax, name: "IVANOV IVAN" },
        ],
        sign: async (_id: string, challenge: string) =>
          btoa(
            JSON.stringify({
              challenge,
              tin: tax,
              name: "IVANOV IVAN",
              org_name: "OOO Polymer Trade",
              pinfl: "31234567890123",
              position: "Director",
            }),
          ),
      };
    },
    [taxId, opts.available] as const,
  );
}

test("E-IMZO onboarding: the certificate registers and confirms the company", async ({
  page,
  request,
}) => {
  const phone = uniquePhone();
  const taxId = uniqueTaxId();
  await stubEimzo(page, taxId, { available: true });
  await login(page, request, phone);

  await page.goto("/companies/new/1");
  await page.getByTestId("account-type-distributor").click();

  // No tax id is typed anywhere: the certificate subject carries the STIR, and
  // the signer creates the company from it. That is the point of signing first.
  await page.getByLabel(/pin/i).fill("123456");
  await page.getByTestId("wizard-eimzo").click();

  // Auto: probe → single cert → create → challenge → sign → verify → confirmed.
  await expect(page.getByTestId("eimzo-success")).toBeVisible({ timeout: 15_000 });

  // The requisites arrive filled and frozen on «Основная информация».
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/companies/new/2");
  await expect(page.getByTestId("wizard-identity-locked")).toBeVisible();
  await expect(page.getByLabel(/tax id|инн|stir/i)).toHaveValue(taxId);
  await expect(page.getByLabel(/tax id|инн|stir/i)).toBeDisabled();
});

test("E-IMZO module missing shows install guidance", async ({ page, request }) => {
  const phone = uniquePhone();
  const taxId = uniqueTaxId();
  await stubEimzo(page, taxId, { available: false });
  await login(page, request, phone);

  await page.goto("/companies/new/1");
  await page.getByLabel(/pin/i).fill("123456");
  await page.getByTestId("wizard-eimzo").click();

  await expect(page.getByTestId("eimzo-module-missing")).toBeVisible();
});

test("signing is gated on the PIN the sheet asks for", async ({ page, request }) => {
  const phone = uniquePhone();
  await stubEimzo(page, uniqueTaxId(), { available: true });
  await login(page, request, phone);

  await page.goto("/companies/new/1");
  await expect(page.getByTestId("wizard-eimzo")).toBeDisabled();
  await page.getByLabel(/pin/i).fill("123456");
  await expect(page.getByTestId("wizard-eimzo")).toBeEnabled();
});
