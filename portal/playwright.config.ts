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
