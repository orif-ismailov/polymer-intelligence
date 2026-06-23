import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e config for the Polymer Intelligence dashboard (Next.js).
 *
 * Business logic under test: staff JWT login + the auth-guarded internal dashboard
 * (live feed, the flagship Purchase Requests master-detail, prices, sources, alerts).
 *
 * Requirements to run:
 *   - The FastAPI backend reachable on http://localhost:8000 with seed data
 *     (dev compose: `docker compose -f deploy/docker-compose.dev.yml up -d postgres redis api`).
 *     Override with BACKEND_ORIGIN.
 *   - `npx playwright install chromium` (one-time).
 *
 * `next dev` is started automatically via the webServer block and proxies /api/* to
 * BACKEND_ORIGIN (see next.config.ts rewrites), so no CORS wiring is needed.
 */
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || "http://localhost:8000";
// Dedicated port: :3000/:3001 are often taken by other dev servers on a shared
// machine, so we start our own dashboard on an uncommon port and never reuse a
// foreign server (reuseExistingServer:false) — reusing the wrong app silently
// runs the suite against someone else's site.
const PORT = Number(process.env.E2E_PORT || 3137);
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // Auth setup writes a storageState; serialize so it lands before dependent specs.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  // Generous timeouts absorb Next dev's first-compile-per-route latency.
  timeout: 60_000,
  expect: { timeout: 15_000 },

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    navigationTimeout: 45_000,
    actionTimeout: 15_000,
  },

  projects: [
    // 1) Log in once via the real UI and persist the refresh cookie.
    { name: "setup", testMatch: /auth\.setup\.ts/ },

    // 2) Authenticated specs reuse the stored cookie; the dashboard layout silently
    //    refreshes the in-memory access token from it on load.
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/admin.json" },
      dependencies: ["setup"],
      testIgnore: [/auth\.setup\.ts/, /auth\.spec\.ts/],
    },

    // 3) Anonymous specs (login-form behavior) run without the stored state.
    {
      name: "anon",
      use: { ...devices["Desktop Chrome"], storageState: { cookies: [], origins: [] } },
      testMatch: /auth\.spec\.ts/,
    },
  ],

  webServer: {
    command: `npm run dev -- --port ${PORT}`,
    url: `${BASE_URL}/login`,
    timeout: 180_000,
    reuseExistingServer: false,
    env: { BACKEND_ORIGIN },
  },
});
