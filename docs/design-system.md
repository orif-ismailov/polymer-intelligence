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
- **dashboard/** (Next + Tailwind + shadcn): same token names in `globals.css`; shadcn theme
  variables mapped onto them so primitives inherit the system. `system` follows `prefers-color-scheme`.
- Tailwind `theme.extend.colors` references the CSS vars so utility classes resolve per-theme.
- Acceptance for any new screen: renders pixel-faithful to its mockup in **both** themes, AA
  contrast on text/controls, and uses only `var(--token)` colors (lint rule: no raw hex in components).
