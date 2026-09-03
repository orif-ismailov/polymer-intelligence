import { expect, test, type Page } from "@playwright/test";

import { confirmIdentityWithEimzo, login, registerCompany } from "./_registration";

/**
 * E-IMZO company-identity confirmation, with a STUBBED CAPIWS bridge (CI has no
 * local module). The bridge is injected on `window.__EIMZO_BRIDGE__`; the backend
 * must run with EIMZO_STUB=true so its gateway accepts the synthetic PKCS#7.
 *
 * **Confirmation is no longer part of registration.** The wizard asks for the ИНН
 * and fills itself from the state registry; a company is confirmed afterwards,
 * from «Статус проверки», where the row already exists. These tests follow it
 * there. Covers: the happy path, the INN rule the backend enforces, and the
 * module-missing path.
 *
 * Prerequisites: live backend on :8000 with DEBUG=true + EIMZO_STUB=true, and
 * OTP_MAX_SENDS_PER_DAY raised (the daily cap is per client IP as well as per
 * phone, so the default 5 blocks repeated runs from one machine).
 */

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

function uniqueTaxId(): string {
  return String(100_000_000 + Math.floor(Math.random() * 899_999_999));
}

/** Inject a stub CAPIWS bridge whose certificate INN is `taxId`. */
async function stubEimzo(page: Page, taxId: string, opts: { available: boolean }): Promise<void> {
  await page.addInitScript(
    ([tax, available]) => {
      (window as unknown as { __EIMZO_BRIDGE__: unknown }).__EIMZO_BRIDGE__ = {
        probe: async () => available,
        listCertificates: async () => [
          { id: "k1", subjectName: "OOO Polymer Trade", tin: tax, name: "IVANOV IVAN" },
        ],
        sign: async (_id: string, challenge: string) => ({
          pkcs7_64: btoa(
            JSON.stringify({
              challenge,
              tin: tax,
              name: "IVANOV IVAN",
              org_name: "OOO Polymer Trade",
              pinfl: "31234567890123",
              position: "Director",
            }),
          ),
          signature_hex: "deadbeef",
        }),
      };
    },
    [taxId, opts.available] as const,
  );
}

test("registration asks for the ИНН and nothing about keys", async ({ page, request }) => {
  const taxId = uniqueTaxId();
  await stubEimzo(page, taxId, { available: true });
  await login(page, request, uniquePhone());

  await page.goto("/cabinet/companies/new/1");
  await page.getByTestId("account-type-distributor").click();
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/2");

  // The certificate picker is gone; the tax id is typed, not read off a key.
  await expect(page.getByTestId("wizard-cert-select")).toHaveCount(0);
  await expect(page.getByLabel(/tax id|инн|stir/i)).toBeEditable();
  await expect(page.getByTestId("wizard-next")).toHaveText(/next|далее|keyingi/i);
});

test("a registered company confirms its identity from the verification screen", async ({
  page,
  request,
}) => {
  const taxId = uniqueTaxId();
  await stubEimzo(page, taxId, { available: true });
  await login(page, request, uniquePhone());

  const companyId = await registerCompany(page, taxId);

  // Unconfirmed until someone signs — registration proves nothing by itself.
  await page.goto(`/cabinet/companies/${companyId}/verification`);
  await expect(page.getByTestId("eimzo-offer")).toBeVisible();

  await confirmIdentityWithEimzo(page, companyId);

  await page.goto(`/cabinet/companies/${companyId}/verification`);
  await expect(page.getByTestId("eimzo-confirmed")).toBeVisible();
  await expect(page.getByTestId("eimzo-offer")).toHaveCount(0);
});

test("a certificate for another company is refused", async ({ page, request }) => {
  const taxId = uniqueTaxId();
  // The key belongs to a DIFFERENT company than the one being confirmed — the
  // rule the backend actually enforces (422 → «ИНН сертификата не совпадает»).
  await stubEimzo(page, uniqueTaxId(), { available: true });
  await login(page, request, uniquePhone());

  const companyId = await registerCompany(page, taxId);

  await page.goto(`/cabinet/companies/${companyId}/verification`);
  await page.getByTestId("eimzo-open").click();
  await expect(page.getByTestId("eimzo-error")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("eimzo-confirmed")).toHaveCount(0);
});

test("E-IMZO module missing shows install guidance", async ({ page, request }) => {
  const taxId = uniqueTaxId();
  await stubEimzo(page, taxId, { available: false });
  await login(page, request, uniquePhone());

  const companyId = await registerCompany(page, taxId);

  await page.goto(`/cabinet/companies/${companyId}/verification`);
  await page.getByTestId("eimzo-open").click();
  await expect(page.getByTestId("eimzo-module-missing")).toBeVisible({ timeout: 20_000 });
});
