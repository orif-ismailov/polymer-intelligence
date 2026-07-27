import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * P0 W2 — the shared/ui kit contract, exercised against the DEV-only gallery at
 * `/dev/ui`. The portal has no unit-test runner, so this spec is the render test
 * for the primitives P1–P6 will build their screens out of: it asserts the
 * variants actually paint from tokens (not stock Tailwind colours) and that the
 * new primitives expose the right semantics/a11y.
 */

const GALLERY = "/dev/ui";
const API_BASE = process.env.PORTAL_API_BASE ?? "http://localhost:8000/api/v1";

function uniquePhone(): string {
  const suffix = String(Math.floor(Math.random() * 1_000_000_000)).padStart(9, "0");
  return `+998${suffix}`;
}

/** OTP login — only needed by the shell test, which must render the real cabinet. */
async function login(page: Page, request: APIRequestContext, phone: string): Promise<void> {
  await page.unrouteAll();
  await page.goto("/login");
  await page.getByLabel(/phone|телефон|telefon/i).fill(phone);
  await page.getByRole("button", { name: /get code|получить код|kod olish/i }).click();

  await page.waitForURL("**/login/code");
  const res = await request.get(`${API_BASE}/portal/auth/otp/peek`, { params: { phone } });
  expect(res.ok()).toBeTruthy();
  const { code } = (await res.json()) as { code: string };
  await page.getByLabel(/code|код|kod/i).fill(code);
  await page.getByRole("button", { name: /sign in|войти|kirish/i }).click();

  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
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
  await login(page, request, uniquePhone());

  await page.setViewportSize({ width: 375, height: 780 });
  const nav = page.getByTestId("ui-bottom-nav");
  await expect(nav).toBeVisible();

  // The bar is fixed, so the end of the content must still clear it once the
  // page is scrolled all the way down — otherwise the last row hides behind it.
  await page.evaluate(() => {
    window.scrollTo(0, document.body.scrollHeight);
  });
  const [barTop, mainBottom] = await Promise.all([
    nav.evaluate((el) => el.getBoundingClientRect().top),
    page.locator("main").evaluate((el) => el.getBoundingClientRect().bottom),
  ]);
  expect(mainBottom).toBeLessThanOrEqual(barTop);

  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(nav).toBeHidden();
});
