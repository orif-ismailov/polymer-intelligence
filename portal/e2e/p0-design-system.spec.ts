import { expect, test, type Page } from "@playwright/test";

/**
 * P0 design-system e2e: the token layer and theme behaviour that every later
 * screen inherits. Deliberately page-agnostic — it asserts the *contract*
 * (dark is default, tokens are green, the switcher persists, contrast passes
 * WCAG AA) rather than any single screen's markup, so P1+ screens can't
 * silently regress the design system.
 *
 * Only `/login` is exercised, so this spec needs a live API on :8000 solely for
 * the SPA to boot — no auth, no seed data.
 */

// ── colour helpers (WCAG 2.1 relative luminance + contrast ratio) ─────────────

interface Rgb {
  r: number;
  g: number;
  b: number;
}

/** Parse `#rgb`, `#rrggbb`, or `rgb(a)(…)` — the forms getComputedStyle returns. */
function parseColor(raw: string): Rgb {
  const value = raw.trim();

  const rgbMatch = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/.exec(value);
  if (rgbMatch) {
    return { r: Number(rgbMatch[1]), g: Number(rgbMatch[2]), b: Number(rgbMatch[3]) };
  }

  const hex = value.replace("#", "");
  const expanded =
    hex.length === 3
      ? hex
          .split("")
          .map((c) => c + c)
          .join("")
      : hex;
  return {
    r: parseInt(expanded.slice(0, 2), 16),
    g: parseInt(expanded.slice(2, 4), 16),
    b: parseInt(expanded.slice(4, 6), 16),
  };
}

function relativeLuminance({ r, g, b }: Rgb): number {
  const channel = (raw: number): number => {
    const c = raw / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(parseColor(a));
  const lb = relativeLuminance(parseColor(b));
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Read design tokens off <html> in one round-trip. */
async function readTokens(page: Page, names: readonly string[]): Promise<Record<string, string>> {
  return page.evaluate((tokenNames) => {
    const styles = getComputedStyle(document.documentElement);
    const out: Record<string, string> = {};
    for (const name of tokenNames) out[name] = styles.getPropertyValue(name).trim();
    return out;
  }, names);
}

const THEME_TOKENS = [
  "--bg",
  "--surface",
  "--surface-2",
  "--surface-inset",
  "--border",
  "--text",
  "--text-muted",
  "--text-subtle",
  "--brand",
  "--brand-fg",
  "--accent-gold",
  "--accent-gold-fg",
  "--danger",
  "--danger-fg",
] as const;

// ── T1.2 — dark is the default theme ─────────────────────────────────────────

test("dark theme is the default for a first-time visitor", async ({ page }) => {
  await page.goto("/login");

  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  // The rendered page must actually be dark, not just labelled dark.
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(relativeLuminance(parseColor(bg))).toBeLessThan(0.05);

  // `color-scheme` must follow so native controls/scrollbars match.
  const colorScheme = await page.evaluate(
    () => getComputedStyle(document.documentElement).colorScheme,
  );
  expect(colorScheme).toBe("dark");
});

// ── T1.1 — the brand is neon green with a dark foreground ────────────────────

test("brand tokens are the neon-green family, not the old blue", async ({ page }) => {
  await page.goto("/login");
  const tokens = await readTokens(page, THEME_TOKENS);

  for (const name of THEME_TOKENS) {
    expect(tokens[name], `${name} must be declared`).not.toBe("");
  }

  // Green dominates the brand accent, and it is clearly not blue-dominant.
  const brand = parseColor(tokens["--brand"]);
  expect(brand.g).toBeGreaterThan(brand.r + 40);
  expect(brand.g).toBeGreaterThan(brand.b + 40);

  // Mockups put DARK text on the green buttons — brand-fg must be dark in dark theme.
  expect(relativeLuminance(parseColor(tokens["--brand-fg"]))).toBeLessThan(0.15);

  // Gold accent (Laboratory Verified / premium badges) is warm: red+green over blue.
  const gold = parseColor(tokens["--accent-gold"]);
  expect(gold.r).toBeGreaterThan(gold.b + 60);
  expect(gold.g).toBeGreaterThan(gold.b + 60);
});

// ── T1.1 — the elevation ladder must not get inverted by a later tweak ───────

test("surface elevation tokens stay visually distinct", async ({ page }) => {
  for (const theme of ["dark", "light"] as const) {
    await page.goto("/login");
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    const tk = await readTokens(page, THEME_TOKENS);

    const lum = (token: string): number => relativeLuminance(parseColor(tk[token]));

    // Each step of the ladder must be *seeable* against its neighbour, or cards
    // and inputs dissolve into their container (which is what the token pass
    // was fixing). Light and dark achieve this in opposite directions — light
    // puts a white card on a grey page, dark lifts the card off black — so only
    // distinctness is asserted here, with direction pinned for dark below.
    for (const [a, b] of [
      ["--surface", "--bg"],
      ["--surface-2", "--surface"],
      ["--surface-inset", "--surface"],
    ] as const) {
      expect(Math.abs(lum(a) - lum(b)), `${theme}: ${a} vs ${b}`).toBeGreaterThan(0.002);
    }

    // Dark is the default and the mockup reference: the card lifts off the page,
    // hover lifts further, and form wells sink below the card.
    if (theme === "dark") {
      expect(lum("--surface")).toBeGreaterThan(lum("--bg"));
      expect(lum("--surface-2")).toBeGreaterThan(lum("--surface"));
      expect(lum("--surface-inset")).toBeLessThan(lum("--surface"));
    }
  }
});

// ── W1 gate — WCAG AA contrast on the token pairs we actually paint with ──────

test("token colour pairs meet WCAG AA in both themes", async ({ page }) => {
  for (const theme of ["dark", "light"] as const) {
    await page.goto("/login");
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);

    const tk = await readTokens(page, THEME_TOKENS);

    // Body / muted / subtle text on every surface level — AA normal text (4.5:1).
    // `--text-subtle` is in here because it paints real content (card meta lines,
    // hints) and not just placeholders: an axe run caught it at 4.02:1 on cards
    // while this spec still passed, because the token was not covered.
    for (const fg of ["--text", "--text-muted", "--text-subtle"] as const) {
      for (const bgToken of ["--bg", "--surface", "--surface-2"] as const) {
        expect(
          contrastRatio(tk[fg], tk[bgToken]),
          `${theme}: ${fg} on ${bgToken}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }

    // Every filled-surface / on-fill-label pair in the system.
    for (const [fg, fill] of [
      ["--brand-fg", "--brand"],
      ["--accent-gold-fg", "--accent-gold"],
      ["--danger-fg", "--danger"],
    ] as const) {
      expect(contrastRatio(tk[fg], tk[fill]), `${theme}: ${fg} on ${fill}`).toBeGreaterThanOrEqual(
        4.5,
      );
    }

    // Brand used as *text*/icon colour on the page background (links, prices).
    expect(
      contrastRatio(tk["--brand"], tk["--bg"]),
      `${theme}: --brand text on --bg`,
    ).toBeGreaterThanOrEqual(4.5);
  }
});

// ── T1.2 — the switcher persists the operator's choice across reloads ────────

test("theme choice persists across a reload", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  // Switching is exposed as a plain <html data-theme> flip driven by the store,
  // so the persistence contract is testable without the Settings screen.
  await page.evaluate(() => {
    localStorage.setItem("portal.theme", "light");
  });
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await page.evaluate(() => {
    localStorage.setItem("portal.theme", "dark");
  });
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

// ── T1.3 — typography: tabular figures available for prices/metrics ─────────

test("numeric type is tabular where numbers are compared", async ({ page }) => {
  await page.goto("/login");

  // `.num` is the design-system-owned utility for figures (styles.css), so it
  // exists regardless of which components happen to reference it.
  const variant = await page.evaluate(() => {
    const probe = document.createElement("span");
    probe.className = "num";
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).fontVariantNumeric;
    probe.remove();
    return value;
  });
  expect(variant).toContain("tabular-nums");
});
