import { test as setup, expect } from "@playwright/test";
import { loginViaUi } from "./helpers";

const AUTH_FILE = "e2e/.auth/admin.json";

/**
 * Logs in once as admin via the real UI and saves the browser storage state
 * (the httpOnly refresh cookie). Authenticated specs reuse it — the dashboard
 * layout silently refreshes the access token from that cookie on load.
 */
setup("authenticate as admin", async ({ page }) => {
  await loginViaUi(page);
  // Sanity: a protected page renders for the authenticated admin.
  await page.goto("/requests");
  await expect(page.getByText(/purchase requests/i).first()).toBeVisible();
  await page.context().storageState({ path: AUTH_FILE });
});
