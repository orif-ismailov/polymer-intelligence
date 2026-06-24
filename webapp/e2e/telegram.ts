/**
 * Telegram Web App test harness: sign valid initData (HMAC-SHA256, the exact
 * algorithm the backend verifies in app/services/client_service.py) and inject a
 * minimal window.Telegram.WebApp so the app authenticates in a plain browser.
 *
 * The BOT_TOKEN must match the backend the suite runs against:
 *   - local dev API: "dev-bot-token-placeholder"
 *   - CI: whatever BOT_TOKEN the e2e backend is started with
 * Override via E2E_BOT_TOKEN.
 */
import crypto from "node:crypto";
import type { Page } from "@playwright/test";

export const BOT_TOKEN = process.env.E2E_BOT_TOKEN || "dev-bot-token-placeholder";

export interface TgUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

/** Build a Telegram-valid, signed initData query string for the given user. */
export function signInitData(
  user: TgUser,
  botToken: string = BOT_TOKEN,
): { raw: string; user: TgUser; authDate: number } {
  const authDate = Math.floor(Date.now() / 1000);
  const params: Record<string, string> = {
    auth_date: String(authDate),
    query_id: "AAE2E-" + authDate,
    user: JSON.stringify(user),
  };
  // data_check_string: sorted "key=value" with DECODED values, joined by \n.
  const dcs = Object.keys(params)
    .sort()
    .map((k) => `${k}=${params[k]}`)
    .join("\n");
  const secret = crypto.createHmac("sha256", "WebAppData").update(botToken).digest();
  const hash = crypto.createHmac("sha256", secret).update(dcs).digest("hex");
  // initData string: URL-encoded values + the hash.
  const raw = Object.entries({ ...params, hash })
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join("&");
  return { raw, user, authDate };
}

/**
 * Open the Web App as an authenticated Telegram buyer at HashRouter route `route`.
 *
 * The app routes with HashRouter (routes live in the URL hash), so we can't pass
 * Telegram launch params in the hash. Instead we (1) neutralise the official
 * telegram-web-app.js — left intact it overwrites window.Telegram with an empty
 * initData on load — and (2) inject a window.Telegram.WebApp shim carrying the
 * signed initData, which getInitData() returns via its non-TMA fallback and i18n
 * reads for language_code.
 */
export async function openApp(
  page: Page,
  route = "/",
  user: TgUser = TEST_BUYER,
  botToken: string = BOT_TOKEN,
): Promise<{ raw: string; user: TgUser }> {
  const { raw } = signInitData(user, botToken);

  await page.route(/telegram-web-app\.js(\?|$)/, (r) =>
    r.fulfill({ contentType: "application/javascript", body: "" }),
  );

  await page.addInitScript(
    ([initData, userJson]) => {
      const noop = () => {};
      const button = {
        setText: noop, show: noop, hide: noop, enable: noop, disable: noop,
        onClick: noop, offClick: noop, setParams: noop,
      };
      (window as unknown as { Telegram: unknown }).Telegram = {
        WebApp: {
          initData,
          initDataUnsafe: { user: JSON.parse(userJson) },
          ready: noop, expand: noop, close: noop,
          colorScheme: "light", themeParams: {},
          MainButton: button, BackButton: button,
          HapticFeedback: { impactOccurred: noop, notificationOccurred: noop, selectionChanged: noop },
        },
      };
    },
    [raw, JSON.stringify(user)] as const,
  );

  // HashRouter URL: "/" → "/#/", "/requests" → "/#/requests".
  await page.goto(`/#${route === "/" ? "/" : route}`);
  return { raw, user };
}

/**
 * Open the app the way Telegram actually launches a Mini App: launch params
 * (including the signed initData) in the URL **hash**. The app must capture initData
 * and strip the tg params so HashRouter doesn't render a blank page.
 */
export async function openViaLaunchHash(
  page: Page,
  user: TgUser = TEST_BUYER,
  botToken: string = BOT_TOKEN,
): Promise<{ raw: string; user: TgUser }> {
  const { raw } = signInitData(user, botToken);
  const hash = new URLSearchParams({
    tgWebAppData: raw,
    tgWebAppVersion: "8.0",
    tgWebAppPlatform: "web",
    tgWebAppThemeParams: "{}",
  }).toString();
  await page.goto(`/#${hash}`);
  return { raw, user };
}

/** A stable default test buyer. */
export const TEST_BUYER: TgUser = {
  id: 555000777,
  first_name: "E2E",
  last_name: "Buyer",
  username: "e2e_buyer",
  language_code: "ru",
};
