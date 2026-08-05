import type { Config } from "tailwindcss";

/**
 * Portal design tokens. Colors read CSS custom properties declared in
 * `src/app/styles.css`, so light/dark theming is a single `data-theme` flip on
 * <html>. Never hardcode hex in components — reference these token-backed names.
 */

/**
 * Make a token colour alpha-capable, so `bg-surface/60` works.
 *
 * Every colour here is a CSS custom property holding a *complete* colour
 * (`#070907`), not the channel triplet Tailwind wants. Given a bare
 * `"var(--bg)"`, Tailwind v3 cannot parse a colour to modulate and there is no
 * `<alpha-value>` placeholder to substitute into, so an opacity modifier makes
 * it drop the declaration **entirely and silently** — the class stays on the
 * element and paints nothing.
 *
 * That was not hypothetical. Measured on the live page before this landed:
 * `bg-bg/95` on the sticky public header and `bg-surface/95` on the cabinet's
 * computed to `rgba(0, 0, 0, 0)` (both bars were transparent, held up only by
 * their `backdrop-blur`), `border-border/60` fell back to preflight's grey, and
 * the hero's `from-bg via-bg/85 to-bg/30` scrim lost its middle stop and its
 * end stop — ~50 such classes across the app. It is exactly the silent failure
 * `docs/design-system.md` P3.1 warns about.
 *
 * `color-mix` fixes it without touching the variables themselves, so
 * `body { background: var(--bg) }`, `--brand-glow`, the `.hero-grid` rules and
 * the e2e token reader all keep seeing a real colour. The alternative —
 * rewriting every token as `7 9 7` channels plus `rgb(var(--bg)/<alpha-value>)`
 * — would break all four of those.
 */
function token(color: string): string {
  const withAlpha = ({ opacityValue }: { opacityValue?: string | number }): string => {
    // Without a modifier Tailwind does not pass `undefined` — it passes the
    // legacy `bg-opacity-*` plumbing, i.e. the literal string
    // `var(--tw-bg-opacity)`. Anything that is not a finite number means "no
    // modifier", and the colour goes through untouched.
    const alpha = Number(opacityValue);
    if (!Number.isFinite(alpha)) return color;
    // Rounded because 0.55 * 100 is 55.00000000000001 in binary floating point,
    // and that lands verbatim in the emitted CSS.
    return `color-mix(in srgb, ${color} ${Math.round(alpha * 10000) / 100}%, transparent)`;
  };
  // Tailwind accepts a function anywhere a colour string is allowed; its own
  // `Config` type models colours as strings only, so the cast sits here, once,
  // at the boundary rather than at each of the twenty call sites below.
  return withAlpha as unknown as string;
}

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: token("var(--bg)"),
        surface: {
          DEFAULT: token("var(--surface)"),
          2: token("var(--surface-2)"),
          inset: token("var(--surface-inset)"),
        },
        border: {
          DEFAULT: token("var(--border)"),
          strong: token("var(--border-strong)"),
        },
        text: {
          DEFAULT: token("var(--text)"),
          muted: token("var(--text-muted)"),
          subtle: token("var(--text-subtle)"),
        },
        brand: {
          DEFAULT: token("var(--brand)"),
          fg: token("var(--brand-fg)"),
          soft: token("color-mix(in srgb, var(--brand) 14%, transparent)"),
          line: token("color-mix(in srgb, var(--brand) 35%, transparent)"),
        },
        // The storefront hero's search field — a deliberately bright plane in
        // both themes, which is why it is its own pair and not a surface tone.
        "hero-field": {
          DEFAULT: token("var(--hero-field)"),
          fg: token("var(--hero-field-fg)"),
        },
        gold: {
          DEFAULT: token("var(--accent-gold)"),
          fg: token("var(--accent-gold-fg)"),
          soft: token("color-mix(in srgb, var(--accent-gold) 14%, transparent)"),
          line: token("color-mix(in srgb, var(--accent-gold) 38%, transparent)"),
        },
        success: token("var(--success)"),
        warning: token("var(--warning)"),
        danger: {
          DEFAULT: token("var(--danger)"),
          fg: token("var(--danger-fg)"),
        },
        info: token("var(--info)"),
        overlay: token("var(--overlay)"),
      },
      boxShadow: {
        glow: "var(--brand-glow)",
        "hero-lift": "var(--hero-lift)",
      },
      borderRadius: {
        lg: "var(--radius-lg)",
        md: "var(--radius-md)",
        sm: "var(--radius-sm)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        /*
         * `Dialog placement="sheet"`. A bottom sheet arrives from the edge it is
         * anchored to — `scale-in` reads as a centred modal no matter where the
         * panel sits, which is exactly the tell that makes a repositioned dialog
         * look like a bug rather than a sheet.
         */
        "sheet-in": {
          from: { opacity: "0", transform: "translate3d(0, 1.5rem, 0)" },
          to: { opacity: "1", transform: "translate3d(0, 0, 0)" },
        },
        spin: {
          to: { transform: "rotate(360deg)" },
        },
        /*
         * Hero decoration. `hero-drift` moves the brand glow behind the headline
         * on a long, low-amplitude loop — at 22s and ±3% it registers as the
         * light being alive rather than as an animation. `hero-rise` is the copy
         * column's entrance.
         *
         * Both are applied through `motion-safe:` at the call site, so a visitor
         * with `prefers-reduced-motion: reduce` gets the static composition.
         */
        "hero-drift": {
          "0%, 100%": { transform: "translate3d(0, 0, 0) scale(1)" },
          "50%": { transform: "translate3d(2%, -3%, 0) scale(1.06)" },
        },
        "hero-rise": {
          from: { opacity: "0", transform: "translate3d(0, 0.5rem, 0)" },
          to: { opacity: "1", transform: "translate3d(0, 0, 0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 150ms ease-out",
        "scale-in": "scale-in 140ms ease-out",
        "sheet-in": "sheet-in 180ms cubic-bezier(0.22, 1, 0.36, 1)",
        spin: "spin 0.8s linear infinite",
        "hero-drift": "hero-drift 22s ease-in-out infinite",
        "hero-rise": "hero-rise 500ms cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [],
};

export default config;
