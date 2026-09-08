import { expect, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

const STAFF_EMAIL = process.env.SEED_ADMIN_EMAIL ?? "admin@polymer.uz";
const STAFF_PASSWORD =
  process.env.SEED_ADMIN_PASSWORD ?? "admin_dev_password_change_in_prod";

export interface Credentials {
  login: string;
  password: string;
}

function unique(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;
}

/**
 * Mint a fresh, usable cabinet account THROUGH THE REAL DOORS.
 *
 * Sign-in stopped being self-service in 0048: an account exists because a staff
 * member issued credentials for it. So the harness does what a staff member does —
 * the public request form, then the admin API — rather than reaching past the app
 * into the database or asking for a dev-only hook. That keeps the provisioning path
 * itself under test, and it is why there is no `otp/peek` equivalent to replace.
 *
 * The forced first-login change is settled here too, over the API, so specs that
 * only need "somebody signed in" are not all walking the same password screen. The
 * screen has its own spec (`registration-audit-login.spec.ts`).
 */
export async function provisionAccount(
  request: APIRequestContext,
  opts: { companyName?: string } = {},
): Promise<Credentials> {
  const phone = `+998${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const login = unique("e2e");

  const applied = await request.post(`${API_BASE}/portal/auth/register`, {
    data: {
      contact_name: "E2E Tester",
      phone,
      company_name: opts.companyName ?? "OOO E2E",
    },
  });
  expect(applied.status(), "registration should be accepted").toBe(202);

  const staff = await request.post(`${API_BASE}/auth/login`, {
    data: { email: STAFF_EMAIL, password: STAFF_PASSWORD },
  });
  expect(staff.ok(), "seeded admin should be able to sign in").toBeTruthy();
  const { access_token: staffToken } = (await staff.json()) as {
    access_token: string;
  };
  const auth = { Authorization: `Bearer ${staffToken}` };

  // The queue, newest first — the application just made is the first row.
  const queue = await request.get(`${API_BASE}/admin/portal-accounts`, {
    headers: auth,
    params: { status: "pending", q: phone },
  });
  expect(queue.ok()).toBeTruthy();
  const [application] = (await queue.json()) as { id: number }[];
  expect(application, `no pending application for ${phone}`).toBeTruthy();

  const issued = await request.post(
    `${API_BASE}/admin/portal-accounts/${application.id}/credentials`,
    { headers: auth, data: { login } },
  );
  expect(issued.ok(), "credentials should be issued").toBeTruthy();
  const temporary = (await issued.json()) as Credentials;

  // Settle the forced first-login change so callers get a ready account.
  const session = await request.post(`${API_BASE}/portal/auth/login`, {
    data: { login: temporary.login, password: temporary.password },
  });
  expect(session.ok(), "the issued credentials should work").toBeTruthy();
  const { access_token: accountToken } = (await session.json()) as {
    access_token: string;
  };

  const password = `${temporary.password}-set`;
  const changed = await request.post(`${API_BASE}/portal/auth/password`, {
    headers: { Authorization: `Bearer ${accountToken}` },
    data: { current_password: temporary.password, new_password: password },
  });
  expect(
    changed.ok(),
    "the first-login password change should succeed",
  ).toBeTruthy();

  return { login: temporary.login, password };
}

/** Sign in with issued credentials, from wherever the page currently is. */
export async function signIn(page: Page, creds: Credentials): Promise<void> {
  await page.getByLabel(/^login|логин|^login$/i).fill(creds.login);
  await page.getByLabel(/password|пароль|parol/i).fill(creds.password);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/cabinet/login"));
}

/** Open the login screen and sign in. The common case. */
export async function login(page: Page, creds: Credentials): Promise<void> {
  await page.goto("/cabinet/login");
  await signIn(page, creds);
}

/**
 * Shared driver for the 5-step company-registration flow
 * («Тип компании → Данные → Банк → Документы → Проверка»).
 *
 * Three specs walk this flow to reach the surface they actually test, and they
 * had three drifting copies of it. Not a `*.spec.ts`, so Playwright's testMatch
 * does not collect it as a suite.
 */

const SKIP = /skip|пропустить|o.tkazib/i;

/** Step 1 — pick an account type. Registration involves no E-IMZO at all. */
export async function stepAccountType(
  page: Page,
  opts: { type?: string } = {},
): Promise<void> {
  await page.goto("/cabinet/companies/new/1");
  await page.getByTestId(`account-type-${opts.type ?? "distributor"}`).click();

  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/2");
}

/**
 * Step 2 — «Основная информация», opening with the ИНН.
 *
 * The registry lookup keys off that field, so on a deployment with the Didox
 * rail on, several of the values typed below arrive already filled; filling them
 * anyway is harmless and keeps the helper working on a stub deployment too.
 */
export async function stepDetails(page: Page, taxId?: string): Promise<void> {
  const name = page.getByLabel(
    /company name|название компании|kompaniya nomi/i,
  );
  if (await name.isEditable()) {
    await name.fill("OOO E2E Test");
  }

  if (taxId != null) {
    const tax = page.getByLabel(/tax id|инн|stir/i).first();
    if (await tax.isEditable()) await tax.fill(taxId);
  }

  await page
    .getByLabel(/legal address|юридический адрес|yuridik manzil/i)
    .first()
    .fill("Tashkent, Amir Temur 123");
  await page
    .getByLabel(/registration date|дата регистрации|ro.yxatdan o.tgan sana/i)
    .fill("2020-03-12");
  await page
    .getByLabel(/ownership form|форма собственности|mulkchilik shakli/i)
    .selectOption("ООО");

  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/3", { timeout: 20_000 });
}

/** Step 3 — bank (skipped) and step 4 — the required registration certificate. */
export async function stepBankAndDocuments(page: Page): Promise<void> {
  await page.getByRole("button", { name: SKIP }).click();
  await page.waitForURL("**/cabinet/companies/new/4");

  await page.setInputFiles('input[type="file"]', {
    name: "registration.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test document"),
  });
  await page.getByTestId("wizard-next").click();
  await page.waitForURL("**/cabinet/companies/new/5");
}

/**
 * Step 5 — «Проверка компании». Arriving submits the case; the CTA unlocks once
 * the company exists, and continuing lands on «Регистрация завершена!».
 */
export async function stepReview(page: Page): Promise<number> {
  const submit = page.getByTestId("wizard-submit");
  await expect(submit).toBeEnabled({ timeout: 20_000 });
  await submit.click();

  await page.waitForURL(/\/cabinet\/companies\/new\/done\/\d+/, {
    timeout: 15_000,
  });
  await expect(page.getByTestId("wizard-done")).toBeVisible();

  const match = /\/cabinet\/companies\/new\/done\/(\d+)/.exec(page.url());
  return Number(match?.[1]);
}

/**
 * Confirm a registered company's identity with E-IMZO, from «Статус проверки».
 *
 * This is now the ONLY door to `identity_locked` — registration no longer signs
 * anything — and with `verification_auto_approve` on it is also how a spec gets a
 * company that may transact. Needs a stub bridge on `window.__EIMZO_BRIDGE__`
 * whose certificate INN matches `taxId`.
 */
export async function confirmIdentityWithEimzo(
  page: Page,
  companyId: number,
): Promise<void> {
  await page.goto(`/cabinet/companies/${companyId}/verification`);
  await page.getByTestId("eimzo-open").click();
  // NOT `eimzo-success`: confirming refetches the company, `identity_locked`
  // flips, and the whole offer block — button, dialog and that success alert —
  // unmounts. The alert is therefore racing its own side effect. The confirmed
  // badge is the state that persists, so it is what this waits on.
  await expect(page.getByTestId("eimzo-confirmed")).toBeVisible({
    timeout: 20_000,
  });
}

/**
 * The whole flow, end to end. Returns the new company's id.
 *
 * `sign` no longer happens inside the wizard: it registers first, then confirms
 * on the verification screen — which is the real user path since E-IMZO left
 * registration, and the only one that still yields a verified company.
 */
export async function registerCompany(
  page: Page,
  taxId: string,
  opts: { type?: string; sign?: boolean } = {},
): Promise<number> {
  await stepAccountType(page, opts);
  await stepDetails(page, taxId);
  await stepBankAndDocuments(page);
  const companyId = await stepReview(page);
  if (opts.sign) await confirmIdentityWithEimzo(page, companyId);
  return companyId;
}
