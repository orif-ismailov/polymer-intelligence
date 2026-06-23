import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e for the Polymer Intelligence Telegram Web App (Vite).
 *
 * Auth: every request carries X-Telegram-Init-Data; the suite injects a signed
 * initData (e2e/telegram.ts) so the app authenticates in a plain browser.
 *
 * Requirements:
 *   - FastAPI backend on http://localhost:8000 with seed data, started with a
 *     BOT_TOKEN matching E2E_BOT_TOKEN (default "dev-bot-token-placeholder").
 *   - `npx playwright install chromium`.
 * Vite proxies /api/* to :8000 (see vite.config.ts), so no CORS wiring is needed.
 */
const PORT = Number(process.env.E2E_WEBAPP_PORT || 5191);
const BASE_URL = `http://localhost:${PORT}`;
// The §6.1.1 cross-app test also drives the dashboard (Next.js), started below.
const DASH_PORT = Number(process.env.E2E_DASH_PORT || 3138);
export const DASHBOARD_URL = `http://localhost:${DASH_PORT}`;
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || "http://localhost:8000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  timeout: 60_000,
  expect: { timeout: 15_000 },

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    navigationTimeout: 45_000,
    actionTimeout: 15_000,
    ...devices["Desktop Chrome"],
  },

  webServer: [
    {
      command: `npm run dev -- --port ${PORT} --strictPort`,
      url: BASE_URL,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      // Dashboard (Next.js) for the cross-app §6.1.1 test; proxies /api to the backend.
      command: `npm run dev -- --port ${DASH_PORT}`,
      cwd: "../dashboard",
      url: `${DASHBOARD_URL}/login`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: { BACKEND_ORIGIN, NEXT_TELEMETRY_DISABLED: "1" },
    },
  ],
});
