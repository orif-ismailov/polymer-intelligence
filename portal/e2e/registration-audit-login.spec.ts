import { expect, test, type APIRequestContext } from "@playwright/test";

import { provisionAccount, signIn } from "./_registration";

/**
 * Cabinet auth audit (0048): login + password, and the request form that replaced
 * self-service sign-up.
 *
 * Replaces `registration-audit-otp.spec.ts`. Access is granted deliberately now —
 * staff issue a login and a password, printed in the contract the parties sign — so
 * what this file audits is the shape of that: one indistinguishable refusal, a
 * request form that promises nothing, and a first-login password change nobody can
 * walk around.
 */

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

test.use({ locale: "ru-RU" });

const STAFF_EMAIL = process.env.SEED_ADMIN_EMAIL ?? "admin@polymer.uz";
const STAFF_PASSWORD =
  process.env.SEED_ADMIN_PASSWORD ?? "admin_dev_password_change_in_prod";

/** An account with credentials that have NEVER been used — still owes the change. */
async function provisionUntouched(
  request: APIRequestContext,
): Promise<{ login: string; password: string }> {
  const phone = `+998${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const login = `e2e-fresh-${Date.now().toString(36)}`;

  await request.post(`${API_BASE}/portal/auth/register`, {
    data: { contact_name: "E2E", phone, company_name: "OOO E2E" },
  });
  const staff = await request.post(`${API_BASE}/auth/login`, {
    data: { email: STAFF_EMAIL, password: STAFF_PASSWORD },
  });
  const { access_token: token } = (await staff.json()) as {
    access_token: string;
  };
  const auth = { Authorization: `Bearer ${token}` };

  const queue = await request.get(`${API_BASE}/admin/portal-accounts`, {
    headers: auth,
    params: { status: "pending", q: phone },
  });
  const [application] = (await queue.json()) as { id: number }[];
  const issued = await request.post(
    `${API_BASE}/admin/portal-accounts/${application.id}/credentials`,
    { headers: auth, data: { login } },
  );
  return (await issued.json()) as { login: string; password: string };
}

// ── Sign-in ───────────────────────────────────────────────────────────────────

test("an empty form keeps the submit button disabled", async ({ page }) => {
  await page.goto("/cabinet/login");
  await expect(page.getByRole("button", { name: "Войти" })).toBeDisabled();
});

test("a wrong password is refused inline, with no navigation", async ({
  page,
  request,
}) => {
  const creds = await provisionAccount(request);

  await page.goto("/cabinet/login");
  await page.getByLabel(/логин/i).fill(creds.login);
  await page.getByLabel(/пароль/i).fill("definitely-not-it");
  await page.getByRole("button", { name: "Войти" }).click();

  await expect(page.getByRole("alert").first()).toContainText(/неверный/i);
  await expect(page).toHaveURL(/\/cabinet\/login$/);
});

test("an unknown login is refused the SAME way as a wrong password", async ({
  page,
  request,
}) => {
  // The whole point of the uniform 401: the screen must not become an oracle for
  // which logins exist. Asserted as text equality, not "both show an error".
  const creds = await provisionAccount(request);

  await page.goto("/cabinet/login");
  await page.getByLabel(/логин/i).fill(creds.login);
  await page.getByLabel(/пароль/i).fill("definitely-not-it");
  await page.getByRole("button", { name: "Войти" }).click();
  const wrongPassword = await page.getByRole("alert").first().innerText();

  await page.reload();
  await page.getByLabel(/логин/i).fill(`nobody-${Date.now()}`);
  await page.getByLabel(/пароль/i).fill("definitely-not-it");
  await page.getByRole("button", { name: "Войти" }).click();
  const unknownLogin = await page.getByRole("alert").first().innerText();

  expect(unknownLogin).toBe(wrongPassword);
});

test("issued credentials sign in", async ({ page, request }) => {
  await page.goto("/cabinet/login");
  await signIn(page, await provisionAccount(request));
  await expect(page).toHaveURL(/\/cabinet/);
});

// ── The forced first-login change ─────────────────────────────────────────────

test("a freshly issued account must change its password before anything else", async ({
  page,
  request,
}) => {
  const creds = await provisionUntouched(request);

  await page.goto("/cabinet/login");
  await signIn(page, creds);
  await expect(page).toHaveURL(/\/cabinet\/password/);

  // And cannot walk around it by typing a URL — the guard sends them back.
  await page.goto("/cabinet/companies");
  await expect(page).toHaveURL(/\/cabinet\/password/);

  const next = `${creds.password}-set`;
  await page.getByLabel(/текущий пароль/i).fill(creds.password);
  await page.getByLabel(/^новый пароль/i).fill(next);
  await page.getByLabel(/повторите/i).fill(next);
  await page.getByRole("button", { name: /сохранить пароль/i }).click();
  await expect(page).toHaveURL(/\/cabinet(?!\/password)/);

  // The old password stops working; the new one is the account's.
  const old = await request.post(`${API_BASE}/portal/auth/login`, {
    data: { login: creds.login, password: creds.password },
  });
  expect(old.status()).toBe(401);
  const fresh = await request.post(`${API_BASE}/portal/auth/login`, {
    data: { login: creds.login, password: next },
  });
  expect(fresh.ok()).toBeTruthy();
});

// ── The access-request form ───────────────────────────────────────────────────

test("the request form promises contact, not access", async ({ page }) => {
  await page.goto("/cabinet/register");
  await page.getByLabel(/ваше имя/i).fill("Иван Петров");
  await page.getByLabel(/компания/i).fill("ООО Полимер");
  await page.getByLabel(/номер телефона/i).fill("+998901234567");
  await page.getByRole("button", { name: /отправить заявку/i }).click();

  await expect(page).toHaveURL(/\/cabinet\/register\/done/);
  await expect(page.getByText(/свяжемся/i)).toBeVisible();

  // No session was created: the cabinet still sends this visitor to the login.
  await page.goto("/cabinet");
  await expect(page).toHaveURL(/\/cabinet\/login/);
});

test("applying twice with the same phone is indistinguishable from applying once", async ({
  request,
}) => {
  const phone = `+998${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const body = { contact_name: "Иван", phone, company_name: "ООО Полимер" };

  const first = await request.post(`${API_BASE}/portal/auth/register`, {
    data: body,
  });
  const second = await request.post(`${API_BASE}/portal/auth/register`, {
    data: body,
  });

  expect(first.status()).toBe(second.status());
  expect(await first.text()).toBe(await second.text());
});
