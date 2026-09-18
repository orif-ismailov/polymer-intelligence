import { expect, test } from "@playwright/test";

/**
 * The storefront home page must hydrate, in a Russian browser, without errors.
 *
 * `/` was the only one of the 39 portal URLs that failed hydration on every
 * load (IMEX-16), and the reason it was the only one is that it is the only
 * page whose components format a number or a date through the **runtime
 * default** locale — `toLocaleString(undefined, …)` and `toLocaleDateString()`
 * with no arguments at all. Those read the ambient locale and time zone of
 * whatever is executing, which is Node in a container (en-US, UTC) on the
 * server and the visitor's own machine (ru-RU, Asia/Tashkent) in the browser.
 * So the server wrote `1,200` and `9/15/2026` into the HTML and the client's
 * first render produced `1 200` and `15.09.2026` — a text mismatch on every
 * offer card and every news row, which React reports as #425 followed by a
 * cascade of #418 and finally #423, discarding the server's markup and
 * re-rendering the page from scratch.
 *
 * The locale/timeZone pair below is the whole test. Under the runner's default
 * en-US the bug is INVISIBLE, because the browser then agrees with Node by
 * coincidence — which is exactly why a green suite and a developer's own
 * browser both missed this for as long as they did.
 *
 * Needs an API whose storefront is not empty: the two offending call sites live
 * inside the offer rail and the news rail, so a `/` with no offers and no news
 * renders neither and passes vacuously. The test says so rather than silently
 * proving nothing.
 */

test.use({ locale: "ru-RU", timezoneId: "Asia/Tashkent" });

const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

/** React's minified hydration complaints, plus the readable dev-build wording. */
const HYDRATION = /Minified React error #(418|423|425)|hydrat|did not match/i;

test("the home page hydrates cleanly in a ru-RU browser", async ({
  page,
  request,
}) => {
  const offers = await request.get(`${API_BASE}/public/offers`, {
    params: { limit: 4 },
  });
  const offerCount =
    (((await offers.json()) as { items?: unknown[] }).items ?? []).length ?? 0;
  test.skip(
    offerCount === 0,
    "storefront has no offers — the offer rail never renders, so this would pass vacuously",
  );

  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));

  // `networkidle` never settles here — the storefront keeps a poller open — so
  // wait on the thing under test instead: the hero, which is the last of the
  // server's markup to be reached by hydration.
  await page.goto("/");
  await expect(page.locator("h1").first()).toBeVisible();
  await page.waitForTimeout(1500);

  expect(errors.filter((e) => HYDRATION.test(e))).toEqual([]);
});
