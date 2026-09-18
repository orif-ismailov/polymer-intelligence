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
    // 1) Authenticated specs sign in PER TEST, via the `test` fixture in helpers.ts.
    //
    //    This used to be a "setup" project that logged in once and saved the refresh
    //    cookie to `e2e/.auth/admin.json`, which every test then replayed. Since
    //    IMEX-1 the refresh token rotates and its predecessor is invalidated, so the
    //    saved cookie was spent by the first test and replayed by all the others —
    //    indistinguishable from a stolen cookie, and treated as one. The family was
    //    revoked and the entire suite landed on the login screen. The application is
    //    right; a shared, replayed session was the thing that had to go.
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      testIgnore: [/auth\.spec\.ts/],
    },

    // 2) Anonymous specs (login-form behavior) run with no session at all.
    {
      name: "anon",
      use: { ...devices["Desktop Chrome"], storageState: { cookies: [], origins: [] } },
      testMatch: /auth\.spec\.ts/,
    },
  ],

  webServer: {
    command: `npm run dev -- --port ${PORT}`,
    // Hit the locale-prefixed login route directly (bare /login 308-redirects to it
    // via the next-intl middleware).
    url: `${BASE_URL}/ru/login`,
    timeout: 180_000,
    reuseExistingServer: false,
    env: { BACKEND_ORIGIN },
  },
});
