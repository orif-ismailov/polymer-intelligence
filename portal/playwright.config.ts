import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the portal e2e suite. It expects the SPA on :5173 and
 * the FastAPI backend on :8000. It is intentionally NOT wired to run in this
 * environment (no live API); it exists as a valid, type-correct harness.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  /*
   * One worker. `fullyParallel: false` only serialises tests *within* a file —
   * Playwright still runs separate spec files concurrently, and several browsers
   * hitting the Vite dev server at once starve its on-demand transforms: the
   * login screens then miss the 30 s timeout and specs fail with no API error
   * (a failing run takes ~34 s, a healthy one ~9 s). These specs also share one
   * backend and one OTP rate-limit bucket per IP, so serial is the honest model.
   * The whole suite runs in ~9 s this way.
   */
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PORTAL_BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
