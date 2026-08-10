import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { registerCompany } from "./_registration";

/**
 * P0 W2 — the shared/ui kit contract, exercised against the DEV-only gallery at
 * `/dev/ui`. The portal has no unit-test runner, so this spec is the render test
 * for the primitives P1–P6 will build their screens out of: it asserts the
 * variants actually paint from tokens (not stock Tailwind colours) and that the
 * new primitives expose the right semantics/a11y.
 */

const GALLERY = "/dev/ui";
const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

function uniqueTaxId(): string {
  return String(Math.floor(Math.random() * 900_000_000) + 100_000_000);
}

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

/** OTP login — only needed by the shell test, which must render the real cabinet. */
async function login(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.unrouteAll();
  await page.goto("/cabinet/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();

  await page.waitForURL("**/cabinet/login/code");
  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  expect(res.ok()).toBeTruthy();
  const { code } = (await res.json()) as { code: string };
  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();

  await page.waitForURL((url) => !url.pathname.startsWith("/cabinet/login"));
}

/** Resolve a CSS custom property to the value the browser computed. */
async function token(page: Page, name: string): Promise<string> {
  return page.evaluate(
    (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim(),
    name,
  );
}

/** Normalise `#rrggbb` / `rgb(...)` / `color(srgb …)` to a comparable `r,g,b` triple. */
function rgbKey(raw: string): string {
  const m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/.exec(raw.trim());
  if (m) return `${Math.round(+m[1])},${Math.round(+m[2])},${Math.round(+m[3])}`;

  // Tokens built with color-mix() (brand-line, brand-soft, gold-*) compute to
  // `color(srgb r g b / a)` with 0–1 components.
  const srgb = /^color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/.exec(raw.trim());
  if (srgb) {
    return [1, 2, 3].map((i) => Math.round(Number(srgb[i]) * 255)).join(",");
  }
  const hex = raw.trim().replace("#", "");
  const full =
    hex.length === 3
      ? hex
          .split("")
          .map((c) => c + c)
          .join("")
      : hex;
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)).join(",");
}

// ── colour maths (shared shape with p0-design-system.spec.ts) ────────────────

interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

function parseRgba(raw: string): Rgba {
  const key = rgbKey(raw);
  const [r, g, b] = key.split(",").map(Number);
  const alpha = /^(?:rgba\([^)]*?[\s,]\/?\s*|color\(srgb[^/)]*\/\s*)([\d.]+)\s*\)/.exec(raw.trim());
  const legacy = /^rgba\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*,\s*([\d.]+)/.exec(raw.trim());
  return { r, g, b, a: Number(alpha?.[1] ?? legacy?.[1] ?? 1) };
}

/** Flatten a translucent colour over an opaque backdrop. */
function composite(fore: string, backdrop: string): string {
  const f = parseRgba(fore);
  const b = parseRgba(backdrop);
  const mix = (x: number, y: number): number => Math.round(x * f.a + y * (1 - f.a));
  return `rgb(${mix(f.r, b.r)}, ${mix(f.g, b.g)}, ${mix(f.b, b.b)})`;
}

function relativeLuminance(color: string): number {
  const { r, g, b } = parseRgba(color);
  const ch = (raw: number): number => {
    const c = raw / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

test.beforeEach(async ({ page }) => {
  // The gallery needs no session, but the app's boot-time silent refresh does:
  // for an anonymous visitor it 401s and the fetch client hard-navigates to
  // /login, taking any route with it. Failing that one call keeps boot on the
  // anonymous path (bootstrap catches, marks auth initialised, no redirect) so
  // the primitives render — no OTP login or seed data needed.
  await page.route("**/portal/auth/refresh", (route) => route.abort());

  await page.goto(GALLERY);
  await expect(page.getByRole("heading", { name: /UI kit/i })).toBeVisible();
});

// ── T2.1 — Button: brand fill with a DARK label, per the mockups ─────────────

test("primary button paints the brand fill with the brand foreground", async ({ page }) => {
  const button = page.getByTestId("ui-button-primary");
  const styles = await button.evaluate((el) => {
    const s = getComputedStyle(el);
    return { bg: s.backgroundColor, fg: s.color };
  });

  expect(rgbKey(styles.bg)).toBe(rgbKey(await token(page, "--brand")));
  expect(rgbKey(styles.fg)).toBe(rgbKey(await token(page, "--brand-fg")));
});

test("a disabled primary button stays legible instead of dimming to mud", async ({ page }) => {
  // Fading a dark label on a green fill to 50% made the label vanish; disabled
  // must drop to a neutral surface with muted (still readable) text.
  const disabled = page.getByTestId("ui-button-disabled");
  const styles = await disabled.evaluate((el) => {
    const s = getComputedStyle(el);
    return { bg: s.backgroundColor, fg: s.color, opacity: s.opacity };
  });

  expect(rgbKey(styles.bg)).not.toBe(rgbKey(await token(page, "--brand")));
  expect(Number(styles.opacity)).toBeGreaterThanOrEqual(0.9);
  expect(rgbKey(styles.fg)).not.toBe(rgbKey(styles.bg));
});

// ── T2.1 — Badge: the mockups' badge family, one component, no inline colour ──

test("badge variants cover the mockup set and use their own tokens", async ({ page }) => {
  await expect(page.getByTestId("ui-badge-verified")).toBeVisible();
  await expect(page.getByTestId("ui-badge-lab")).toBeVisible();
  await expect(page.getByTestId("ui-badge-in-stock")).toBeVisible();
  await expect(page.getByTestId("ui-badge-on-order")).toBeVisible();

  // Laboratory Verified is the gold one; Verified is the green one. They must
  // not resolve to the same colour (that regression is easy to introduce).
  const labColor = await page
    .getByTestId("ui-badge-lab")
    .evaluate((el) => getComputedStyle(el).color);
  const verifiedColor = await page
    .getByTestId("ui-badge-verified")
    .evaluate((el) => getComputedStyle(el).color);

  expect(rgbKey(labColor)).toBe(rgbKey(await token(page, "--accent-gold")));
  expect(rgbKey(verifiedColor)).not.toBe(rgbKey(labColor));

  // The verified badge carries the mockups' check mark.
  await expect(page.getByTestId("ui-badge-verified").locator("svg")).toBeVisible();
});

// ── T2.1 — badges are legible on their own tinted fill, in BOTH themes ───────

test("badge label contrast clears AA on every tinted variant and tone", async ({ page }) => {
  // Buttons are in here too, on purpose. The token-level contrast spec only
  // proves the *pairs* are sound; it cannot see a label colour that never
  // reaches the element. `text-danger-fg` did exactly that — the class was on
  // the button while its rule was missing, so the label fell back to body text
  // on a red fill at 2.98:1. Measuring what the browser actually painted is the
  // only check that catches it.
  const ids = [
    "ui-badge-verified",
    "ui-badge-lab",
    "ui-badge-in-stock",
    "ui-badge-on-order",
    "ui-button-primary",
    "ui-button-danger",
    "ui-button-disabled",
  ] as const;

  for (const theme of ["dark", "light"] as const) {
    // Go through the stored preference so the app's own bootstrap applies it —
    // poking `data-theme` from a test gets reverted by ThemeProvider on re-render,
    // which quietly makes an assertion measure the wrong theme.
    await page.evaluate((t) => localStorage.setItem("portal.theme", t), theme);
    await page.goto(GALLERY);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

    for (const id of ids) {
      const { fg, bg } = await page.getByTestId(id).evaluate((el) => {
        const s = getComputedStyle(el);
        return { fg: s.color, bg: s.backgroundColor };
      });
      // Tinted fills are translucent, so the effective backdrop is the card
      // behind them; compose the badge tint over it before measuring.
      const surface = await token(page, "--surface");
      expect(contrastRatio(fg, composite(bg, surface)), `${theme}: ${id}`).toBeGreaterThanOrEqual(
        4.5,
      );
    }
  }

  await page.evaluate(() => localStorage.setItem("portal.theme", "dark"));
});

// ── T2.1 — Card accent: the thin green outline from the module cards ─────────

test("accent card is outlined in the brand colour", async ({ page }) => {
  const plain = await page
    .getByTestId("ui-card-plain")
    .evaluate((el) => getComputedStyle(el).borderTopColor);
  const accent = await page
    .getByTestId("ui-card-accent")
    .evaluate((el) => getComputedStyle(el).borderTopColor);

  expect(rgbKey(accent)).not.toBe(rgbKey(plain));
  // The accent border is a brand-derived tint, so its green channel dominates.
  const [r, g, b] = rgbKey(accent).split(",").map(Number);
  expect(g).toBeGreaterThan(r);
  expect(g).toBeGreaterThan(b);
});

// ── T2.1 — form controls sit in the inset well, not flush with the card ──────

test("inputs paint the inset surface so they read as fields", async ({ page }) => {
  const inset = rgbKey(await token(page, "--surface-inset"));
  for (const id of ["ui-input", "ui-select", "ui-textarea"]) {
    const bg = await page.getByTestId(id).evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(rgbKey(bg), id).toBe(inset);
  }
});

// ── T2.2 — StatusStepper: the vertical deal/contract timeline ────────────────

test("status stepper marks done, current and pending steps distinctly", async ({ page }) => {
  const stepper = page.getByTestId("ui-status-stepper");
  await expect(stepper).toBeVisible();

  // Semantics, not colours: the current step is the a11y "step" cursor.
  await expect(stepper.locator('[aria-current="step"]')).toHaveCount(1);
  await expect(stepper.getByRole("listitem")).toHaveCount(4);

  const states = await stepper
    .getByRole("listitem")
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-state")));
  expect(states).toEqual(["done", "done", "current", "pending"]);
});

// ── T2.2 — ProgressRing: the AI-check dial ──────────────────────────────────

test("progress ring exposes its value to assistive tech", async ({ page }) => {
  const ring = page.getByTestId("ui-progress-ring");
  await expect(ring).toHaveAttribute("role", "progressbar");
  await expect(ring).toHaveAttribute("aria-valuenow", "76");
  await expect(ring).toHaveAttribute("aria-valuemin", "0");
  await expect(ring).toHaveAttribute("aria-valuemax", "100");
  await expect(ring).toContainText("76");
});

// ── T2.2 — StatChip: the metric tile, with non-jittering figures ─────────────

test("stat chip renders value + label with tabular figures", async ({ page }) => {
  const chip = page.getByTestId("ui-stat-chip");
  await expect(chip).toContainText("50 000+");
  await expect(chip).toContainText("Проверенных компаний");

  const variant = await chip
    .getByTestId("ui-stat-chip-value")
    .evaluate((el) => getComputedStyle(el).fontVariantNumeric);
  expect(variant).toContain("tabular-nums");
});

// ── T2.2 — BottomNav: mobile-only, per the mockups ───────────────────────────

test("bottom nav shows on mobile and hides on desktop", async ({ page }) => {
  const nav = page.getByTestId("ui-bottom-nav");

  await page.setViewportSize({ width: 375, height: 780 });
  await expect(nav).toBeVisible();

  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(nav).toBeHidden();
});

test("bottom nav marks the active route and surfaces unread counts", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 780 });
  const nav = page.getByTestId("ui-bottom-nav");

  // Exactly one destination is current, and the badge count is announced.
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
  await expect(nav.getByTestId("ui-bottom-nav-badge")).toHaveText("3");
});

// ── The cabinet shell actually uses the bar on phones (P0 definition of done) ──

test("the authenticated shell shows the bottom bar on phones only", async ({ page, request }) => {
  // A company is required, not incidental: `RequireCompany` sends a companyless
  // account to `/cabinet/onboarding`, which sits outside `AppShell` and so has
  // no bottom bar to assert on. This test is about the SHELL, so it has to get
  // past the registration gate first.
  await login(page, request, uniquePhone());
  await registerCompany(page, uniqueTaxId());
  // The wizard ends on `/cabinet/companies/new/done/:id`, which is deliberately
  // outside `AppShell` — step into the cabinet proper to get the shell.
  await page.goto("/cabinet");

  await page.setViewportSize({ width: 375, height: 780 });
  const nav = page.getByTestId("ui-bottom-nav");
  await expect(nav).toBeVisible();

  // The bar is fixed, so the end of the content must still clear it once the
  // page is scrolled all the way down — otherwise the last row hides behind it.
  // Settle first: the cabinet home grows as its queries resolve, and scrolling
  // to a height measured before that leaves the page part-way down.
  await page.waitForLoadState("networkidle");
  await page.evaluate(async () => {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  });
  const [barTop, mainBottom] = await Promise.all([
    nav.evaluate((el) => el.getBoundingClientRect().top),
    page.locator("main").evaluate((el) => el.getBoundingClientRect().bottom),
  ]);
  expect(mainBottom).toBeLessThanOrEqual(barTop);

  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(nav).toBeHidden();
});

// ── Wave 1 primitives (portal restyle) ───────────────────────────────────────
//
// Added, never edited: the twelve assertions above are P0's contract and stay
// exactly as they were. These cover the six primitives the restyle introduces.

test("page header renders a real h1 with its back link and action slot", async ({ page }) => {
  const header = page.getByTestId("ui-page-header");
  await expect(header).toBeVisible();

  // Load-bearing: the flow specs locate screens by `heading, level: 1`.
  await expect(header.locator("h1")).toHaveText("PP H030 GP");
  await expect(header.getByRole("link", { name: /назад/i })).toBeVisible();
  await expect(header.getByRole("button", { name: /RFQ/i })).toBeVisible();
});

test("tabs mark exactly one option pressed in each variant", async ({ page }) => {
  for (const id of ["ui-tabs-underline", "ui-tabs-pill"] as const) {
    const group = page.getByTestId(id);
    await expect(group).toBeVisible();
    await expect(group.locator('[aria-pressed="true"]')).toHaveCount(1);

    // Selecting another option moves the pressed state rather than adding one.
    await group.getByRole("button").nth(1).click();
    await expect(group.locator('[aria-pressed="true"]')).toHaveCount(1);
  }

  // Counts beside a label are figures, so they line up down a column of tabs.
  const counted = page.getByTestId("ui-tabs-underline").locator("span.num").first();
  await expect(counted).toHaveCSS("font-variant-numeric", /tabular-nums/);
});

test("spec list is a definition list and marks its numeric values tabular", async ({ page }) => {
  // `SpecList` stamps the testid on every instance, and the gallery now renders
  // a second one (the `justified` receipt shape) — this test is about the first,
  // `stacked`, block.
  const list = page.getByTestId("ui-spec-list").first();
  await expect(list).toBeVisible();
  expect(await list.evaluate((el) => el.tagName)).toBe("DL");

  // Label above value, both present — the mockups' contract data block.
  await expect(list.locator("dt").first()).toHaveText(/номер договора/i);
  await expect(list.locator("dd.num").first()).toHaveCSS(
    "font-variant-numeric",
    /tabular-nums/,
  );
});

test("spec tiles sit on the card surface with the label above the value", async ({ page }) => {
  const tile = page.getByTestId("ui-spec-tile").first();
  await expect(tile).toBeVisible();
  expect(rgbKey(await tile.evaluate((el) => getComputedStyle(el).backgroundColor))).toBe(
    rgbKey(await token(page, "--surface")),
  );

  const box = await tile.boundingBox();
  const valueBox = await tile.locator("p").boundingBox();
  expect(valueBox!.y).toBeGreaterThan(box!.y);
});

test("file rows show the name, the meta line and their actions", async ({ page }) => {
  const row = page.getByTestId("ui-file-row").first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("SDS_PP_H030GP.pdf");
  await expect(row).toContainText(/2\.4 MB/);
  await expect(row.getByRole("button", { name: /скачать/i })).toBeVisible();

  // A superseded document is struck through rather than removed.
  const muted = page.getByTestId("ui-file-row").nth(1);
  await expect(muted.locator("p").first()).toHaveCSS("text-decoration-line", /line-through/);
});

test("gold button paints the gold token pair and clears AA in both themes", async ({ page }) => {
  // Same reasoning as the badge-contrast test: a colour class that never reaches
  // the element is invisible to token-level maths, so measure what was painted.
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => localStorage.setItem("portal.theme", t), theme);
    await page.goto(GALLERY);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

    const { fg, bg } = await page.getByTestId("ui-button-gold").evaluate((el) => {
      const s = getComputedStyle(el);
      return { fg: s.color, bg: s.backgroundColor };
    });
    expect(rgbKey(bg), `${theme}: fill`).toBe(rgbKey(await token(page, "--accent-gold")));
    expect(rgbKey(fg), `${theme}: label`).toBe(rgbKey(await token(page, "--accent-gold-fg")));

    const surface = await token(page, "--surface");
    expect(contrastRatio(fg, composite(bg, surface)), `${theme}: AA`).toBeGreaterThanOrEqual(4.5);
  }

  await page.evaluate(() => localStorage.setItem("portal.theme", "dark"));
});

test("sticky action bar clears the bottom nav on phones and goes static on desktop", async ({
  page,
}) => {
  const bar = page.getByTestId("ui-sticky-action-bar");
  const nav = page.getByTestId("ui-bottom-nav");

  await page.setViewportSize({ width: 375, height: 780 });
  await expect(bar).toBeVisible();
  expect(await bar.evaluate((el) => getComputedStyle(el).position)).toBe("fixed");

  // The bar sits ON TOP of the nav, not over it.
  const [barBottom, navTop] = await Promise.all([
    bar.evaluate((el) => el.getBoundingClientRect().bottom),
    nav.evaluate((el) => el.getBoundingClientRect().top),
  ]);
  expect(barBottom).toBeLessThanOrEqual(navTop + 1);

  /*
   * And the content clears the BAR, not just the nav. The existing shell test
   * measures `main.bottom <= nav.top`, which a fixed bar cannot violate — a bar
   * covering the last row of content passes it silently. This is the assertion
   * that actually holds the `pb-36` rule in place.
   */
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const lastContentBottom = await page
    .locator("section")
    .last()
    .locator("p")
    .evaluate((el) => el.getBoundingClientRect().bottom);
  const barTop = await bar.evaluate((el) => el.getBoundingClientRect().top);
  expect(lastContentBottom).toBeLessThanOrEqual(barTop);

  /*
   * The same two assertions again, with an iPhone's home-indicator inset.
   *
   * Everything above is measured under `env(safe-area-inset-bottom): 0`, which
   * is what every desktop browser and every headless run reports — and under a
   * zero inset the two bars cannot collide, so the checks pass whatever the
   * arithmetic is. That is precisely how `bottom-14` shipped: it cleared
   * `BottomNav`'s `h-14` ROW but not the row plus the `pb-[env(...)]` the nav
   * also carries, so on a real iPhone 34px of the bar sat behind the nav and the
   * action labels were sliced through. Nothing in this suite could see it.
   *
   * The inset cannot be set from Playwright (no `env()` override, and the iOS
   * device descriptors report 0 too), so it is substituted into exactly the two
   * declarations that read it. Not a mock of the bug — a mock of the DEVICE.
   */
  const INSET = 34; // iPhone 12–16, portrait
  await page.setViewportSize({ width: 375, height: 780 });
  await page.addStyleTag({
    content: `
      [data-testid="ui-bottom-nav"] { padding-bottom: ${INSET}px !important; }
      .bottom-nav { bottom: calc(3.5rem + ${INSET}px) !important; }
      .pb-action-bar { padding-bottom: calc(9rem + ${INSET}px) !important; }
    `,
  });

  const inset = await bar.evaluate((el) => {
    const nav = document.querySelector('[data-testid="ui-bottom-nav"]')!;
    const navTop = nav.getBoundingClientRect().top;
    const navBorder = parseFloat(getComputedStyle(nav).borderTopWidth);
    // The deepest painted box inside the bar, not the bar's own edge: with
    // `!p-0` (which `OfferActionBar` passes) those are the same, and the labels
    // are what a visitor notices being cut.
    const deepest = Math.max(
      ...[...el.querySelectorAll("*")].map((n) => n.getBoundingClientRect().bottom),
    );
    return { overlap: deepest - (navTop + navBorder) };
  });
  expect(inset.overlap, "bar content behind the bottom nav with an iOS inset").toBeLessThanOrEqual(0);

  await page.setViewportSize({ width: 1280, height: 900 });
  expect(await bar.evaluate((el) => getComputedStyle(el).position)).toBe("static");
});

// ── Registration primitives (the redesigned company-registration flow) ───────

test("radio cards expose real radios and mark exactly one selected", async ({ page }) => {
  const group = page.getByTestId("ui-radio-cards");
  const radios = group.locator('input[type="radio"]');
  expect(await radios.count()).toBeGreaterThan(1);

  /*
   * The selection has to live on a real <input type="radio">: a styled <div> is
   * what this primitive replaced, and it took arrow-key group navigation and
   * screen-reader semantics with it. `sr-only` keeps it focusable — `hidden`
   * or `display:none` would not be.
   */
  await page.getByTestId("ui-radio-card-buyer").click();
  await expect(group.locator('input[value="buyer"]')).toBeChecked();
  await expect(group.locator('input[value="distributor"]')).not.toBeChecked();

  /*
   * The chosen card is outlined in the brand colour, not merely tinted.
   * `toHaveCSS` rather than a one-shot read: the native radio flips `checked`
   * synchronously on click, so the paint is still one React commit behind.
   */
  const brand = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--brand").trim(),
  );
  const [r, g, b] = rgbKey(brand).split(",");
  await expect(page.getByTestId("ui-radio-card-buyer")).toHaveCSS(
    "border-top-color",
    `rgb(${r}, ${g}, ${b})`,
  );
});

test("segmented tabs share one track and press exactly one option", async ({ page }) => {
  const strip = page.getByTestId("ui-tabs-segmented");
  await expect(strip.locator('button[aria-pressed="true"]')).toHaveCount(1);

  // The whole group is one control: the track is bordered, the items are not.
  const trackBorder = await strip.evaluate((el) => getComputedStyle(el).borderTopWidth);
  expect(parseFloat(trackBorder)).toBeGreaterThan(0);
});

test("checklist rows carry their outcome beyond colour alone", async ({ page }) => {
  const rows = page.getByTestId("ui-checklist").locator("li");
  expect(await rows.count()).toBeGreaterThan(2);

  /*
   * Every state must be readable without colour vision, so the outcome is
   * spelled out in the status line rather than carried by the tint. The row also
   * declares its state, which is what keeps the mark, the tint and the words
   * from drifting apart.
   */
  for (const state of ["passed", "running", "warning"]) {
    const row = page.locator(`[data-testid="ui-checklist"] li[data-state="${state}"]`).first();
    await expect(row).toBeVisible();
    expect((await row.innerText()).trim().length, `${state} row states its outcome`).toBeGreaterThan(0);
  }
});

test("checklist status lines clear AA in both themes", async ({ page }) => {
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);

    for (const state of ["passed", "warning", "failed", "running", "pending"]) {
      const line = page.locator(`[data-testid="ui-checklist"] li[data-state="${state}"] p + p`);
      if ((await line.count()) === 0) continue;
      const { color, backdrop } = await line.first().evaluate((el) => {
        let node: HTMLElement | null = el.parentElement;
        let bg = "rgb(255, 255, 255)";
        while (node) {
          const value = getComputedStyle(node).backgroundColor;
          if (!/rgba\(0, 0, 0, 0\)|transparent/.test(value)) {
            bg = value;
            break;
          }
          node = node.parentElement;
        }
        return { color: getComputedStyle(el).color, backdrop: bg };
      });
      expect(
        contrastRatio(color, backdrop),
        `${theme}: checklist ${state} status line`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  }
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
});

test("the date field shows one calendar affordance, not the UA's as well", async ({ page }) => {
  const field = page.locator("input.date-field").first();
  await expect(field).toBeVisible();

  /*
   * `<input type="date">` paints `::-webkit-calendar-picker-indicator` from the
   * system accent — on the dark inset well that is a pale wedge sitting next to
   * our brand glyph, two calendars on one field. styles.css hides it.
   *
   * The rule is asserted through the stylesheet rather than `getComputedStyle`:
   * author overrides on a UA-internal pseudo are not reported there (it answers
   * "inline-block" even when the indicator is demonstrably gone), so reading it
   * would fail a working field. What can silently break is the rule vanishing
   * from the bundle, and that is exactly what this sees.
   */
  const rulePresent = await page.evaluate(() =>
    [...document.styleSheets].some((sheet) => {
      try {
        return [...sheet.cssRules].some(
          (rule) =>
            rule.cssText.includes("calendar-picker-indicator") &&
            rule.cssText.includes("date-field"),
        );
      } catch {
        return false; // cross-origin sheet
      }
    }),
  );
  expect(rulePresent, "styles.css must hide the UA picker indicator").toBe(true);

  // …and the design-system affordance that replaces it is there, exactly once.
  await expect(field.locator("xpath=..").getByRole("button")).toHaveCount(1);
});

test("a password field masks by default and reveals on demand", async ({ page }) => {
  const field = page.getByTestId("ui-password-input");
  await expect(field).toHaveAttribute("type", "password");

  // The reveal lives inside the well; `Input`'s adornment slot is otherwise
  // pointer-transparent, so a click landing here proves the exception works.
  const toggle = field.locator("xpath=..").getByRole("button");
  await toggle.click();
  await expect(field).toHaveAttribute("type", "text");
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
});

test("the stacked stepper shows every label at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  const labels = page.getByTestId("ui-stepper-stacked").locator("li > span:last-child");
  expect(await labels.count()).toBe(5);

  /*
   * Five steps on a 375 px phone give each label ~65 px. Truncating «Тип
   * компании» to «Тип комп…» removes the one thing the rail exists to say, so
   * the labels wrap instead — asserted as "nothing is clipped".
   */
  for (let i = 0; i < 5; i += 1) {
    const clipped = await labels.nth(i).evaluate((el) => el.scrollWidth > el.clientWidth + 1);
    expect(clipped, `step ${i + 1} label is clipped`).toBe(false);
  }
  await page.setViewportSize({ width: 1280, height: 900 });
});

/*
 * The add-product primitives (`ChoiceTile`, `Segmented`, `Radio`, `ChipInput`,
 * `Dropzone`, `StepPanel`). Each one exists because the mockups' add-product
 * sheets use a control the kit did not have, and each is easy to re-implement
 * wrongly at a call site — so the contract is asserted here, not in the flow.
 */

test("a choice tile is a real radio and paints its chosen state", async ({ page }) => {
  const tiles = page.getByTestId("ui-choice-tiles");
  const inputs = tiles.getByRole("radio");
  await expect(inputs).toHaveCount(2);

  // The visible tile is a label around a hidden input: selection must be
  // readable from the control, not only from the paint.
  await expect(inputs.nth(0)).toBeChecked();
  await inputs.nth(1).check();
  await expect(inputs.nth(1)).toBeChecked();
  await expect(inputs.nth(0)).not.toBeChecked();

  // …and the chosen tile carries the gold border the mockup gives it, from the
  // token rather than a stock palette class.
  const chosen = tiles.locator("label").nth(1);
  const border = await chosen.evaluate((el) => getComputedStyle(el).borderTopColor);
  expect(rgbKey(border)).toBe(rgbKey(await token(page, "--accent-gold")));
});

test("the segmented control reports its state to assistive tech", async ({ page }) => {
  const group = page.getByTestId("ui-segmented");
  await expect(group).toHaveAttribute("role", "radiogroup");

  const options = group.getByRole("radio");
  await expect(options.nth(0)).toHaveAttribute("aria-checked", "true");
  await options.nth(1).click();
  await expect(options.nth(1)).toHaveAttribute("aria-checked", "true");
  await expect(options.nth(0)).toHaveAttribute("aria-checked", "false");
});

test("radio rows share one group", async ({ page }) => {
  const rows = page.getByTestId("ui-radio").getByRole("radio");
  await expect(rows).toHaveCount(2);
  await rows.nth(1).check();
  await expect(rows.nth(0)).not.toBeChecked();
});

test("the chip input commits on Enter and removes a chip", async ({ page }) => {
  const field = page.getByTestId("ui-chip-input");
  const chips = field.locator("li");
  const before = await chips.count();

  await field.getByRole("textbox").fill("Высокая жёсткость");
  await field.getByRole("textbox").press("Enter");
  await expect(chips).toHaveCount(before + 1);
  await expect(field.getByText("Высокая жёсткость")).toBeVisible();

  // Every chip carries its own labelled ✕ — a bare glyph would be unreachable.
  await field.getByRole("button", { name: /Убрать: Высокая жёсткость/ }).click();
  await expect(chips).toHaveCount(before);
});

test("the dropzone opens a picker and hides its input", async ({ page }) => {
  const zone = page.getByTestId("ui-dropzone");
  await expect(zone).toBeVisible();

  // The input is visually hidden but must still be a real file input, or the
  // drop target is the only way in and keyboard users are locked out.
  const input = page.locator('input[type="file"][accept="application/pdf"]');
  await expect(input).toHaveCount(1);
  await expect(input).not.toBeVisible();
});

test("a step panel numbers its sheet and states the counter", async ({ page }) => {
  const panel = page.getByTestId("ui-step-panel");
  await expect(panel.getByRole("heading", { level: 2 })).toHaveText("Наличие / Под заказ");
  await expect(panel.getByText("Шаг 3 из 7")).toBeVisible();
  await expect(panel.getByText("3", { exact: true }).first()).toBeVisible();
});
