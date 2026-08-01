# PetroAI — Design System

> The visual contract for the PetroAI Mini App and internal dashboard. Goal: **pixel-identical
> to the approved mockups (IMG_0043/0044/0046), in both dark and light themes, from one shared
> component set.** Phase 1 builds against this document.
>
> **Canonical sources:** IMG_0046 (unified bottom-tab navigation) is the source of truth for
> app structure/navigation. IMG_0043 / IMG_0044 are the source of truth for inner buyer/seller
> screen details. Where they conflict, IMG_0046 wins.

## 1. Principles

Premium **B2B "Bloomberg-terminal × fintech"**: dark-first, data-dense but clean, generous
spacing, rounded surfaces, high-contrast semantic accents. Professional, fast, trustworthy —
built for petrochemical traders, not consumers.

## 2. Theme architecture

- **Tokens are CSS custom properties.** Components reference `var(--token)` only — never raw hex.
- Two themes: `:root` = **dark** (default brand look); `[data-theme="light"]` overrides the same
  token names. Nothing else changes between themes.
- **Resolution order at runtime:**
  1. Manual override saved on the client profile (`clients.theme_pref ∈ {system, light, dark}`,
     surfaced in the **Профиль** page).
  2. If `theme_pref = system` (default) → follow Telegram's `WebApp.colorScheme`
     (`@telegram-apps/sdk`) and live-update on its `themeChanged` event.
  3. Dashboard (non-Telegram) → `system` follows `prefers-color-scheme`.
- A single `ThemeProvider` sets `data-theme` on `<html>` and persists the override.
- **Shared across `webapp/` and `dashboard/`** so Mini App and internal dashboard read as one
  product. Tailwind's theme extension is wired to the same CSS variables.

## 3. Color tokens

Hex values are the contract. Bright accents are deepened one step in light mode to pass WCAG AA
on white. Status uses **tinted-bg + dark-text** chips in light mode (not glowing fills).

### Neutrals
| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0A0E14` | `#F6F8FB` | app canvas |
| `--surface` | `#121826` | `#FFFFFF` | cards, inputs, rows |
| `--surface-2` | `#1A2130` | `#EEF2F7` | nested/hover surface |
| `--border` | `#1E2533` | `#E6EAF0` | hairline borders, dividers |
| `--text` | `#F5F7FA` | `#0E1422` | primary text, values |
| `--text-muted` | `#8A93A6` | `#5B6678` | labels, captions, placeholders |
| `--overlay` | `rgba(0,0,0,.6)` | `rgba(16,20,34,.4)` | modal scrim |
| `--shadow` | none (use surfaces) | `0 1px 2px rgba(16,20,34,.06), 0 4px 12px rgba(16,20,34,.08)` | card elevation (light) |

### Semantic accents (per §4 mapping)
| Token | Dark | Light | Meaning |
|---|---|---|---|
| `--green` | `#22C55E` | `#16A34A` | Market + primary CTA + prices |
| `--green-on` | `#062D17` | `#FFFFFF` | text/icon on green fill |
| `--blue` | `#2F6BFF` | `#2557E6` | Buyer info + Telegram + "Открыть Mini App" |
| `--orange` | `#F5851F` | `#E0700C` | Seller flow + Продать tab |
| `--purple` | `#8B5CF6` | `#7C3AED` | News + Новости tab |
| `--danger` | `#EF4444` | `#DC2626` | required `*`, negative deltas, destructive |

### Status / tinted chips (bg / text pairs)
| Token | Dark bg/text | Light bg/text | Use |
|---|---|---|---|
| `--chip-ok` | `rgba(34,197,94,.16)` / `#22C55E` | `#E9F8EF` / `#15803D` | "В наличии", "Проверен", +delta |
| `--chip-warn` | `rgba(245,133,31,.16)` / `#F5851F` | `#FEF1E3` / `#B45309` | "на модерации" |
| `--chip-down` | `rgba(239,68,68,.16)` / `#EF4444` | `#FDECEC` / `#B91C1C` | −delta, "отклонено" |
| `--chip-neutral` | `rgba(138,147,166,.16)` / `#8A93A6` | `#EEF2F7` / `#5B6678` | inactive/draft |

## 4. Accent semantics (confirmed canonical)

| Color | Domain | Applied to |
|---|---|---|
| **Green** `--green` | Market / Buy / money | global primary CTA ("Далее", "Купить сырьё"), prices, in-stock & verified badges, positive deltas, Маркет tab |
| **Blue** `--blue` | Buyer info / Telegram | buyer-request section icon, Telegram contact, "Открыть Mini App", Заявки tab accent |
| **Orange** `--orange` | Sell | seller wizard primary button, seller section icon, **Продать** tab |
| **Purple** `--purple` | News | news section icon, **Новости** tab |

Primary CTA is **green everywhere**; the seller wizard's primary button is **orange** (its domain
color). Tab active state uses each tab's domain color.

## 5. Typography

Geometric sans — **Inter** (web), falling back to the Telegram/system stack
(`-apple-system, "SF Pro Text", "Segoe UI", Roboto, …`). RU/EN/TR/UZ Latin+Cyrillic coverage.

| Role | Size / weight / line | Notes |
|---|---|---|
| Screen title | 20 / 700 / 26 | centered in top bar |
| Section heading | 17 / 600 / 24 | "Информация о продукте" |
| Field label | 13 / 500 / 18 | muted; trailing red `*` if required |
| Body | 15 / 400 / 22 | default |
| Caption / hint | 12 / 400 / 16 | `--text-muted` |
| **Price (lg)** | 24 / 700 / 28 | `--green`, e.g. "1 200 USD/MT" |
| Price unit | 13 / 500 | muted, trails the value |
| Button | 16 / 600 | — |

## 6. Spacing, radius, elevation

- **Spacing scale (px):** 4 · 8 · 12 · 16 · 20 · 24 · 32. Page padding 16. Field gap 12. Section gap 24.
- **Radius:** input/card `--r-md: 14`, button `--r-md`, chip/pill `--r-full: 999`, modal `--r-lg: 20`, thumbnail `--r-sm: 10`.
- **Elevation:** dark = flat, separated by `--surface`/`--border`; light = `--shadow`. No borders+shadow doubling in light (border lightens to `--border`, shadow carries depth).
- **Hit targets:** ≥ 44px; bottom-tab icons 24px + 11px label.

## 7. Component specs

One implementation each; both themes via tokens.

- **Button** — full-width, `--r-md`, 48px tall, 16/600. Primary = `--green` fill + `--green-on`.
  Seller-primary = `--orange` fill. Secondary = `--surface` fill + `--border` + `--text`.
  Disabled = `--chip-neutral`.
- **Text input / select** — `--surface` fill, 1px `--border`, `--r-md`, 48px, label above, muted
  placeholder, chevron for selects. Focus ring = domain accent at 40% alpha. Paired suffix
  selector for **unit** (MT/тонны) and **currency** (USD/UZS/EUR/RUB).
- **Step indicator** — circles 1…N joined by 2px connectors. Done/active = flow accent fill +
  `--green-on`; upcoming = `--surface` + `--border` + `--text-muted`. Subtitle "Шаг N из M".
- **Bottom tab bar** — 5 slots: Маркет · Заявки · **＋ center (Продать)** · Новости · Профиль.
  `--surface` bg, top `--border`, 24px icon + label; active tab = its domain color; **count badge**
  (e.g. Заявки "2") = `--danger`/accent dot with number.
- **Category chips** — pill, scrollable row. Active = `--green` fill + `--green-on`; inactive =
  `--surface` + `--border` + `--text-muted`. (Все · HDPE · PP · LDPE · PVC · PET)
- **Offer / product card** — thumbnail (`--r-sm`) · name (15/600) · grade caption · **price (lg green)**
  · qty + location pin (`--text-muted`) · seller row with "✓ Проверен" `--chip-ok` badge · contact
  icon buttons (phone `--green`, Telegram `--blue`, WhatsApp `--green`). Optional ratings (👍/👎) +
  views (👁) for the chat surface.
- **Selection card (radio)** — full-width row, `--surface`, selected = accent border + `--green`
  check glyph. Used for delivery location + urgency.
- **Hint banner** — `--surface-2` bg, info icon, caption text ("Не знаете точную марку?").
- **Summary box** — "Ваша заявка": key (`--text-muted`) → value (`--text`) rows on `--surface-2`.
- **Success state** — centered green check in ring + AI-brain illustration (subtle glow in dark,
  flat tint in light) + reassurance copy + primary/secondary buttons.
- **File upload** — "Выбрать файл" / "Добавить фото" dashed `--border` dropzone; thumbnails up to
  10; per-file name + size + remove; document rows for TDS / паспорт качества / сертификат.
- **Phone field** — UZ flag + `+998` mask prefix.
- **Status badge** — maps to `--chip-*`: ok (В наличии/Проверен/Опубликовано), warn (на модерации),
  down (отклонено), neutral (черновик).
- **News report card** — chat-bubble style on `--surface`: title 📈 + date, country blocks with
  flags, product rows with green(+)/red(−) deltas, 🤖 AI Summary block, timestamp; inline action
  buttons row (last = blue "Открыть Mini App").

## 8. Iconography & imagery

- **Icons:** line style, 1.5–2px stroke, 24px grid — `lucide-react` (already used in both apps).
- **Flags:** country emoji/flag chips in prices & news (🇨🇳/🇮🇷/🇺🇿).
- **Product imagery:** real pellet/granule photos in offer cards; rounded `--r-sm`; placeholder =
  `--surface-2` with a polymer glyph when absent.

## 9. Screen catalog (maps tokens → mockups)

| Surface | Mockup | Tab |
|---|---|---|
| Market catalog + search + chips + offer cards | IMG_0043 ②, IMG_0046 ① | Маркет |
| Offer / product detail card | IMG_0043 ③ | (from Маркет) |
| Buyer wizard 5 steps + success | IMG_0044 top, IMG_0046 ② | Заявки |
| Seller wizard 5 steps + moderation | IMG_0043/0044 bottom, IMG_0046 ③ | Продать |
| News feed / daily report | IMG_0046 ④ | Новости |
| Общий чат (listing feed) | IMG_0044 right | (later; chat surface) |
| Profile (company, language, **theme override**, role pref) | — | Профиль |

## 10. Localization

Four locales — **`ru` (default)**, `en`, `tr`, `uz` — across webapp, dashboard, and bot
templates. All component copy comes from message catalogs; no hard-coded strings. Layouts must
tolerate longer DE/EN/TR strings (no fixed-width labels). Numbers/prices: thin-space grouping
("1 200"), currency suffix per field.

## 11. Implementation notes

- **webapp/** (Vite): tokens in a global stylesheet (`src/styles/tokens.css`), `ThemeProvider`
  using `@telegram-apps/sdk` `colorScheme` + `themeChanged`, override persisted via profile API.
- **dashboard/** (Next + Tailwind + shadcn): `globals.css` uses shadcn's own HSL-based token names
  (`--background`, `--card`, `--primary`, etc.) — a different naming system from the webapp's
  tokens — reconciled to the same locked Polymer Intelligence color values via `tailwind.config.ts`
  (see the mapping table in `globals.css`'s own header comment). `system` follows `prefers-color-scheme`.
- Tailwind `theme.extend.colors` references the CSS vars so utility classes resolve per-theme.
- Acceptance for any new screen: renders pixel-faithful to its mockup in **both** themes, AA
  contrast on text/controls, and uses only `var(--token)` colors (lint rule: no raw hex in components).

## 12. Reconciliation (`docs/design.jpeg` ↔ `docs/design_2.jpeg`)

Two approved mockup sheets exist. `design.jpeg` (= IMG_0043/0044/0046, dark-navy) is the
canonical base; `design_2.jpeg` is a later green-primary variant with refreshed copy and two new
surfaces. The Mini App implements **design_2's copy + screen set on design.jpeg's documented
accent semantics** (§4). Where the two sheets disagree, the resolution and the flag:

| Conflict | design.jpeg | design_2.jpeg | Implemented | Flag |
|---|---|---|---|---|
| Buyer primary CTA color | blue "Купить сырьё" | green | **green** (§4 "primary CTA = green everywhere") | ⚠️ design.jpeg's blue not used |
| Seller publish CTA color | — | green | **orange** (§4 seller-domain) | ⚠️ design_2's green not used |
| Главный экран | Market catalog | intro landing (AI Marketplace, stats, bullets, dual CTA) | new **Home** landing at `/` (`pages/Home.tsx`); Market keeps the catalog | — |
| Bottom navigation | ＋FAB (Маркет·Заявки·**＋Продать**·Новости·Профиль) | flat Главная·Заявки·Маркет·Новости·Профиль | **flat design_2 nav** (Главная·Заявки·Маркет·Новости·Профиль, no FAB); selling is reached from Home's "Продать сырьё" CTA | ⚠️ supersedes the IMG_0046 FAB layout in §7 |
| Buyer wizard length | catalog→single form | **4 steps** (Продукт→Условия→Контакты→Доп.) | 4 steps + success | — (supersedes the earlier "5 steps" note in §9) |
| New surfaces | — | "Как это работает?", "Чат-поддержка", seller "Проверка и публикация", "Общий чат" | `pages/HowItWorks.tsx`, `pages/Support.tsx`, seller wizard step 4 review; "Общий чат" listing feed = the Маркет catalog | — |

Copy is verbatim from the sheets, in `webapp/src/i18n/{ru,uz,tr,en}.json` (ru = source of truth).

---

# Part II — IMEX AI portal (`portal/`)

> Added by `.planning/deal-lifecycle/P0-DESIGN-SYSTEM.md`. **Scope: `portal/` only.**
> Everything above (Part I) governs `webapp/` (frozen) and `dashboard/` (internal, not
> restyled) and is unchanged. The portal is the client-facing surface and follows the
> IMEX AI mockups in **`docs/new-design/`** (12 sheets + README catalog).

## P1. Principles

Dark-first, near-black graphite with a **neon-green** brand and a **gold** accent for
lab/premium marks. Data-dense but airy: large radii, hairline borders, tabular figures,
one bright accent per view. **Dark is the default theme**; light is the secondary theme,
recoloured to the same brand rather than designed separately.

## P2. Colour tokens

Declared in `portal/src/app/styles.css`; `portal/tailwind.config.ts` maps utility names onto
them, so a theme is one `data-theme` flip on `<html>`.

| Token | Dark (default) | Light | Use |
|---|---|---|---|
| `--bg` | `#070907` | `#f5f8f6` | page canvas |
| `--surface` | `#101512` | `#ffffff` | card |
| `--surface-2` | `#1a211c` | `#eef2ef` | raised / hover / secondary button |
| `--surface-inset` | `#0a0d0b` | `#f7faf8` | form wells (inputs sit *below* their card) |
| `--border` | `#2b342e` | `#dfe6e1` | hairline |
| `--border-strong` | `#3e4a43` | `#c3ccc6` | outline-button border |
| `--text` | `#e9efea` | `#0d1210` | body text, values |
| `--text-muted` | `#9aa59d` | `#515c56` | labels, captions |
| `--text-subtle` | `#848f89` | `#616b65` | meta lines, placeholders |
| `--brand` | `#22c55e` | `#0d6e31` | CTAs, prices, active nav, links |
| `--brand-fg` | `#052e10` | `#ffffff` | label **on** the brand fill |
| `--accent-gold` | `#eab308` | `#8a6100` | Laboratory Verified, premium, in-flight steps |
| `--accent-gold-fg` | `#241a00` | `#ffffff` | label on the gold fill |
| `--success` / `--warning` / `--danger` / `--info` | `#22c55e` / `#eab308` / `#f05252` / `#58b8f0` | `#0d6e31` / `#8a6100` / `#b91c1c` / `#1d6fa5` | status |
| `--danger-fg` | `#2b0505` | `#ffffff` | label on the danger fill |
| `--hero-field` / `--hero-field-fg` | `#f2f6f3` / `#0c110e` | `#ffffff` / `#0d1210` | the storefront hero's search field — the one control that stays **bright in both themes** |
| `--overlay` | `rgb(0 0 0 / .62)` | `rgb(9 14 11 / .45)` | modal + drawer scrim |
| `--brand-glow` | `0 0 24px` brand@35% | `0 0 20px` brand@22% | glow under accent CTAs (`shadow-glow`) |
| `--hero-lift` | `0 18px 50px` black@38% | `0 10px 26px` `#090e0b`@10% | lift under a control floating on a photo (`shadow-hero-lift`) |
| `--radius-lg` / `-md` / `-sm` | `1rem` / `.75rem` / `.5rem` | same | cards / controls / chips |

Derived Tailwind names: `brand-soft` / `brand-line` (brand at 14% / 35%), `gold-soft` /
`gold-line`, `surface-inset`, `shadow-glow`, `shadow-hero-lift`, `.num`.

Values are not arbitrary — every one is pinned by the contrast test in P5. In light theme
`--brand` is darker than the mockups' neon so that **both** white-on-fill and
brand-as-text-on-`brand-soft` clear AA. `--success` is now that same darkened green for the
same reason: `bg-success/10` did not paint until the alpha fix below, so the badge label had
only ever been measured against plain white, and the real tint put it at 4.44:1.

### Alpha on a token colour

`bg-surface/60` works — but it did not until `tailwind.config.ts` grew `token()`. Every
colour here is a custom property holding a *complete* colour, and given a bare `var(--bg)`
Tailwind v3 has nothing to modulate and no `<alpha-value>` slot to fill, so it drops the
declaration **entirely and silently**. Measured before the fix: `bg-bg/95` on the public
header and `bg-surface/95` on the cabinet topbar both computed to `rgba(0,0,0,0)` — the bars
were transparent, held up only by their `backdrop-blur` — and the hero's
`from-bg via-bg/85 to-bg/30` scrim lost two of its three stops. `token()` wraps each colour
in `color-mix`, which leaves the variables themselves untouched for `body`, `--brand-glow`,
`.hero-grid` and the e2e token reader.

**Two rules follow, and both fail silently:**

1. **A bare opacity modifier must come from `theme.opacity`, which steps by 5.** `bg-bg/88`
   and `bg-info/8` compile to nothing at all. Use `/90`, `/10`, or bracket it: `bg-bg/[.88]`.
2. **When a translucent fill starts painting, re-measure what sits on it.** The tint you just
   turned on is a new backdrop, and the token behind it was chosen against the old one.

## P3. Rules for new screens

1. **No colour literals.** No hex, no stock Tailwind palette (`blue-600`, `slate-800`), no
   `text-white`. A new colour is a new token in `styles.css` + `tailwind.config.ts`.
   *Watch for silently-dead classes:* `accent` was referenced 17 times across 11 files
   without ever being defined, so those hovers and focus rings rendered as nothing.
   If a colour class does not visibly change anything, check it exists in the config.
2. **Compose from `shared/ui`.** Don't restyle a primitive at the call site; add a variant
   to it. Semantic props over colour props: `<Badge variant="verified">`, not
   `<Badge tone="success" icon={…}>`.
3. **Figures use `.num`** (tabular) wherever numbers are compared down a column — prices,
   MOQ, volumes, metric tiles, timestamps.
4. **Both themes, every time.** Check light too; it is secondary, not optional.
5. **Restart the dev server after touching `tailwind.config.ts`.** Vite does not always pick
   up config changes, and a missing utility fails *silently* — the class stays on the element
   and the property just falls back (this is how `text-danger-fg` shipped a 2.98:1 button
   through a passing token test).

## P4. Primitive catalog (`portal/src/shared/ui`)

| Primitive | Notes |
|---|---|
| `Button` | `primary` (brand fill, dark label, glow on hover) · `outline` (the mockups' partner CTA) · `secondary` · `ghost` · `glass` · `danger` · `gold`. `glass` is `outline` for a control that sits on a **photograph**: same silhouette, laid on a blurred `surface/70` plate, because a transparent button's label contrast is otherwise whatever pixel happens to be behind it. Disabled is a **neutral** surface, never a faded fill. |
| `Badge` | `variant`: `verified` · `lab-verified` (gold) · `in-stock` · `on-order`, each with its glyph; or plain `tone`. Never wraps. |
| `Card` | `variant="accent"` for the mockups' brand-outlined module cards. |
| `Stepper` | Horizontal wizard progress: ticks for done, filled glowing disc for active. |
| `StatusStepper` | Vertical timeline for long processes (contract signing, escrow, deal): green done, gold in flight, hollow pending. `data-state` per row. |
| `StatChip` | Metric tile (`50 000+` / label), tabular. |
| `ProgressRing` | Circular dial (AI-check screens); a real `progressbar` for AT. |
| `BottomNav` | Phone-only bottom bar; the shell wires it in `widgets/app-shell/MobileNav`. Screens it covers need bottom padding. |
| `BrandLogo` | IMEX AI lockup. **Interim** — swap the `<svg>` when the operator delivers the vector. |
| `PageHeader` | The chrome every screen opens with: optional back chevron, `<h1>`, inline badge slot, subtitle, right-hand `actions`. Owns the page-title rung so no screen picks a font size for its own header. The `<h1>` is load-bearing — the e2e flows find screens with `getByRole("heading", { level: 1 })`. |
| `Tabs` | The two switcher shapes: `underline` (product detail, company profile, trade room) and `pill` (market filters, deal scopes). Optional per-item `count` and `testId`. Deliberately **not** `role="tablist"` — these filter a list that lives outside them, and a tablist with no matching `tabpanel` is an axe violation where a toggle button is not. Class strings live in `tabStyles.ts`, a sibling `.ts`, because exporting a helper beside a component from a `.tsx` trips `react-refresh/only-export-components` and fails `--max-warnings 0`. |
| `SpecList` / `SpecItem` | The key/value `<dl>`. `stacked` (label above value) where the grid *is* the content; `inline` (`label: value`) inside list cards. The variant travels by context, not per item, so a list can't end up with one mismatched row. `numeric` marks a value tabular. |
| `SpecTile` | Bordered fact tile — icon, label, value. Not a `StatChip` variant: StatChip is figure-first with the figure pinned as its own test id; this is label-first. |
| `FileRow` | Document row: glyph, name, `kind · size · date` meta, optional status badge, trailing actions. `muted` strikes through a superseded document. |
| `StickyActionBar` | The sheets' phone action bar, pinned above `BottomNav`; a plain static row at `md`. **A page using it must add `pb-36 md:pb-0`** — a fixed element does not extend `<main>`'s box, so without it the bar covers the last row of content and the bottom-nav clearance test cannot see it. |
| `icons.tsx` | The glyph set the primitives need. The portal ships no icon dependency. |

## P6. Type and spacing

Not in `tailwind.config.ts`, on purpose. A named utility (`text-h1`) renames the call-site
decision instead of removing it, and **nothing in the gate can see a font size** — every
pinned assertion measures a colour, a contrast ratio, an ARIA attribute, a `data-*` value or
a literal string. A wrong scale would ship through a fully green suite. `<PageHeader/>`,
`Tabs`, `SpecList` and `CardTitle` own these rungs instead; the table is what they encode.

| Role | Class string |
|---|---|
| Hero (auth screens) | `text-2xl font-semibold leading-tight sm:text-3xl` |
| Page title (`h1`) | `text-2xl font-semibold text-text` |
| Page subtitle | `mt-1 text-sm text-text-muted` |
| Section / card title | `text-base font-semibold text-text` |
| Body | `text-sm text-text` |
| Label / caption | `text-xs text-text-muted` (meta lines: `text-text-subtle`) |
| Hero figure (price, escrow amount) | `num text-2xl font-semibold leading-tight text-brand` |
| Metric tile figure | `num text-xl font-semibold` |
| Nav / tab label | `text-sm font-medium`; bottom nav `text-[11px]` |

Rhythm: page root `space-y-5` · card body `space-y-4` · title→subtitle `mt-1` ·
label→value `mt-0.5` · card padding `px-5 py-4` (already in `CardHeader`/`CardBody`) ·
phone bottom padding `pb-24` (in `AppShell`), `pb-36` on a screen with a `StickyActionBar`.

**If you are typing `text-2xl` or `<h1>` in a page file, you are re-implementing a primitive.**

## P5. Enforcement

The portal has no unit-test runner, so the design system is pinned by Playwright:

- `portal/e2e/p0-design-system.spec.ts` — dark-is-default, the green brand family, the
  surface elevation ladder, switcher persistence, `.num`, and **WCAG AA on every token pair
  we paint with, in both themes**.
- `portal/e2e/p0-ui-kit.spec.ts` — every primitive rendered on the DEV-only gallery at
  **`/dev/ui`**, asserting variants resolve to their tokens and that *rendered* badge and
  button labels clear AA (token maths alone cannot see a rule that never reached the element).
- `/dev/ui` is also the fastest way to eyeball a token change against the mockups.

axe-core (`wcag2a` + `wcag2aa`) run on `/cabinet/login`, `/market`, `/cabinet/companies/:id`
and `/dev/ui` in
both themes: **0 violations**. Two were found and fixed during P0 — `--text-subtle` at 4.02:1
on cards, and brand-on-`brand-soft` badges at 4.19:1 in light theme.

### What the gate cannot see

Worth knowing before you trust a green run:

- **No page is ever measured in the light theme.** Every both-themes assertion is either
  token-level or against `/dev/ui`. A `bg-surface/95 backdrop-blur` bar that disappears on a
  white page ships green. Eyeball light on every screen you touch.
- **Nothing measures page width.** A tab strip inside a grid column silently widened the
  market offer page to 401px at a 375px viewport instead of scrolling, because a grid item's
  automatic minimum size is its content's min-content and `overflow-x-auto` does not break
  that chain. `Tabs` carries `min-w-0 max-w-full`; a column containing one needs `min-w-0` too.
- **A fixed bar cannot violate `main.bottom <= nav.top`.** That is why the sticky-bar test
  measures against the bar itself, and why `pb-36` is a rule rather than a suggestion.
- **Nothing switches locale.** A key added to `ru.json` alone crashes `uz`/`en` at runtime.
  Prefer passing labels as props (`PageHeader`'s `backLabel`) — `shared/ui` imports no i18n.
- **No contrast assertion can see text on a photograph.** Token maths compares two flat
  colours; the storefront hero paints over a JPEG, where the backdrop varies per pixel and
  per breakpoint. Measure it by hand: hide the text runs (`visibility: hidden`), screenshot,
  then sample the composited pixels inside each run's box and take the *worst* ratio, not the
  average. Doing that on the hero found three failures a green suite could not: the light
  theme's popular-query row at 3.81:1 (the search shell's drop shadow), and the mobile
  subtitle and chip label at 1.85:1 and 1.57:1 (a scrim too thin for the sunlit part of the
  frame). Re-run it at 390 **and** desktop, in both themes, whenever the scrim, the crop or
  the copy's position changes.
