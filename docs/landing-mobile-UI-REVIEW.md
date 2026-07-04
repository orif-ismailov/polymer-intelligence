# IMEX AI Landing — Mobile UI Review

**Audited:** 2026-07-03
**Baseline:** Abstract 6-pillar standards + project brand contract (webapp/CLAUDE.md)
**Viewport target:** ~390px wide (Telegram Mini App + plain mobile browser)
**Screenshots:** 5 provided (pre-fix snapshots of deployed build at docs/Screenshot 2026-07-03 at 22.58.44–23.00.26.png)
**Registry audit:** Skipped (no shadcn/components.json in webapp/)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Strong RU marketing voice; "AI" cap inconsistency in nav duplicate + footer dead links |
| 2. Visuals | 2/4 | Globe nodes clip/crowd at ≤390px; hero grid stacks globe below fold with no transition state shown |
| 3. Color | 4/4 | 60/30/10 distribution correct; all contrast ratios pass WCAG AA; hardcoded values minimal and intentional |
| 4. Typography | 3/4 | Scale is coherent; 12.5px sub-pixel size and 10px node labels edge accessibility; no fluid scale below 560px on body text |
| 5. Spacing | 2/4 | Sticky CTA bar overlaps in-page footer buttons; step desc max-width 220px too narrow for single-column mobile; safe-area inset present but padding-bottom override order risky |
| 6. Experience Design | 2/4 | Redundant triple CTA (hero, final-CTA section, sticky bar) with no scroll-position awareness; 5 nav items hidden on mobile with no hamburger; footer link buttons are non-functional dead ends |

**Overall: 16/24**

---

## Top 3 Priority Fixes

1. **Globe nodes overflow/clip at 390px** — Users see node labels ("Поставщики (заводы, НПЗ)") truncated or pushed outside the visible column, breaking the hero's primary value-communication visual. The `@media (max-width: 560px)` block shrinks `.imex-viz` to `max-width: 300px` and `.imex-node { width: 82px }`, but node labels with two-line Russian text ("Анализ рынка в реальном времени") at `font-size: 10px` still overflow the 82px container at the left-edge node (left: 18%). **Fix:** Reduce node label verbosity in i18n or add `overflow: hidden; text-overflow: ellipsis` on `.imex-node__label`; alternatively move to abbreviated single-word labels for the globe ("Поставщики", "Покупатели") and put full descriptions in the hero feature cards only.

2. **Sticky CTA bar covers footer content / creates triple-CTA redundancy** — The fixed `.imex-sticky-cta` bar is permanently visible throughout the entire scroll journey. It overlaps the `.imex-footer__bar` bottom content (privacy/terms) on phones. There is also a hero CTA pair and a final-CTA section pair — three instances of identical "Купить сырьё / Продать сырьё" within one page. **Fix:** Show the sticky bar only after the user has scrolled past the hero CTAs (IntersectionObserver on `.imex-hero__ctas`); hide it when the footer is in view. Increase `padding-bottom` on `.imex-landing` for the ≤560px block or increase `.imex-footer` bottom padding to guarantee the legal bar is never clipped.

3. **Mobile nav is non-existent — five nav links hidden with no affordance** — `.imex-lh__nav { display: none }` at mobile with no hamburger. On a long-scroll landing page this leaves the user with no way to jump to "Как это работает", "Преимущества", "Партнёры" etc. from the header. This is particularly damaging in the Telegram Mini App context where swipe-back is captured by Telegram, not the page. **Fix:** Add a compact hamburger/drawer for mobile, or convert the header nav to a horizontal pill-scroll row (no wrapping) at mobile with overflow-x: auto.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)

**What passes:**
- CTA verbs are specific and action-oriented: "Купить сырьё" / "Продать сырьё" — no generic "Submit" or "OK" found.
- Section tags ("КАК ЭТО РАБОТАЕТ", "НАШИ ПАРТНЁРЫ") are all-caps, spaced, consistent.
- Step descriptions are concise and user-benefit framed (ru.json lines approx. s1–s4).
- Trust line "Безопасные сделки и полная конфиденциальность" appears twice (hero + sticky bar top) — appropriate reinforcement not redundancy.
- The "1 000+" stat with space-as-thousands-separator is stylistically consistent with RU locale convention; `white-space: nowrap` fix in landing.css line 421 prevents the visible wrap seen in Screenshot 23.00.26.

**Issues:**

- **WARNING — Nav duplicate key** (Landing.tsx line 248–251): NAV array has both `{ key: "about", id: "how" }` and `{ key: "how", id: "how" }` — both scroll to the same `#how` anchor. "О платформе" and "Как это работает" are distinct concepts but share a destination. This is a logic bug that also looks like copy confusion if the nav were ever visible on mobile. `needs_human_review: true` — confirm which section should "О платформе" scroll to (perhaps a brand/mission block that doesn't yet exist, or a page-top scroll).

- **WARNING — Footer buttons are dead UI** (Landing.tsx lines 511–512): "FAQ" and "Поддержка 24/7" are `<button>` elements with no onClick handler. They render as interactive elements that do nothing when tapped — a broken interaction on mobile. Same for Privacy / Terms buttons (lines 518–519).

- **WARNING — Partner "Iran" tile i18n key** (Landing.tsx line 172): `{t("landing.partners.iran")}` renders "Иранские НПЗ и заводы" in the screenshot (23.00.26). This is a description, not a company name, inconsistent with all other partner tiles which display brand names (LUKOIL, SINOPEC). `needs_human_review: true` — should be "NIOC" or the Farsi transliteration to match the pattern.

- **MINOR — Feature strip stat label** (ru.json): "покупателей (заводы, фабрики, компаний)" has a grammatical case mismatch in RU ("компаний" is genitive but "покупателей" is genitive too — the bracketed list reads oddly as a gloss). `needs_human_review: true`.

---

### Pillar 2: Visuals (2/4)

**What passes:**
- Hero visual hierarchy is clear in screenshot 22.58.44: badge → wordmark (IMEX AI large) → title → paragraph → feature cards → CTA buttons.
- Dark panel cards with thin `rgba(255,255,255,0.07)` borders create depth against the `#05070A` canvas.
- Neon green AI core pulsing animation (landing.css line 355–358) creates a clear focal point on the globe.
- Partner logo tiles fall back gracefully to branded text + Factory icon (Landing.tsx lines 326–328) — no broken-image gaps.
- `loading="lazy"` on partner logos and CTA photo prevents jank on initial load.

**Issues:**

**BLOCKER — Globe node collision and overflow at 390px viewport** (Screenshot 22.59.58):
Node positions are set as inline `left/top` percentages in Landing.tsx lines 421–426. The four nodes are at left: 18%, 27%, 73%, 82% and top: 23%/63%. After the `@media (max-width: 560px)` fix, `.imex-viz` is `max-width: 300px` centered. At 300px container width:
- Node at `left: 18%` = 54px from left edge. With `width: 82px` and `transform: translate(-50%, -50%)`, left edge lands at 54 − 41 = 13px — barely inside the container, but the Russian text "Анализ рынка в реальном времени" (3 words) at 10px in an 82px box wraps to 3–4 lines and the rendered height may push the label below the container boundary.
- Node at `left: 82%` = 246px, right edge at 246 + 41 = 287px — within 300px, but tight.
- The SVG connecting lines (viewBox 400×400 absolute-positioned) map coordinates designed for a ~460px visual; at 300px the lines' endpoint circles (at x=72, x=328) map to (72/400)×300 = 54px and (328/400)×300 = 246px — which don't align with the absolutely-positioned node badges, creating a visible disconnect between the SVG lines and the node elements.

**WARNING — Globe section to "How it works" transition** (Screenshot 22.59.58): The globe appears as a standalone block between the hero content and the next panel. On mobile, there is no section header visible at this scroll position — the globe floats with significant empty space above "КАК ЭТО РАБОТАЕТ". This creates a perceived dead zone in the scroll.

**WARNING — Hero trust line and CTA proximity** (Screenshot 22.58.44): The sticky bar immediately duplicates the hero CTAs. On first load the user sees four CTA buttons on screen (2 in hero, 2 sticky). The hierarchy of primary vs secondary actions collapses.

**WARNING — Barrels fallback illustration**: The CSS barrels (`imex-barrel`) are a best-effort approximation. If the Unsplash image fails to load, 5 simple rectangles with green accent stripes appear. This is acceptable as a fallback but is noticeably low-fidelity for a marketing page selling premium B2B products. `needs_human_review: true` — self-hosting the polymer-granules image is recommended.

---

### Pillar 3: Color (4/4)

**Distribution analysis:**
- 60% neutral: `#05070A` (canvas), `#0b0f15` / `#0e141c` (panels), `#10151d` (ghost button bg) — correctly dominant.
- 30% text: `#EEF2F6` (primary text), `#8B97A8` (muted) — adequate readability layer.
- 10% accent: `#5CFF6E` neon green used on: AI wordmark, badge, node circles, step icons, feat icons, feat count, button fill, CTA art accent lines, footer contact icons, footer brand wordmark, ambient glow. Total ~12 distinct element types — borderline overuse but all are functional accent usages, not decorative inflation.

**Contrast ratios (WCAG AA minimum 4.5:1 for small text, 3:1 for large):**
- `#8B97A8` on `#05070A` (page bg): **6.81:1** — PASS
- `#8B97A8` on `#0b0f15` (panel bg): **6.48:1** — PASS
- `#8B97A8` at 10px (node label, ≤560px): contrast passes (6.8:1) but 10px is below any reasonable readability floor — see Typography.
- `#04220b` (primary btn text) on `#5CFF6E`: **12.9:1** — PASS, excellent.
- `#EEF2F6` on `#10151d` (ghost btn): **16.27:1** — PASS.

**Hardcoded values:** Only `#0d1219` (partner tile bg, landing.css line 393) and `#04220b` (primary btn text color, line 189) appear outside CSS custom properties. Both are intentional and brand-consistent; not flags.

No issues requiring a score deduction.

---

### Pillar 4: Typography (3/4)

**Scale in use (mobile):**

| Size | Usage |
|------|-------|
| 10px | `.imex-node__label` (≤560px breakpoint) |
| 11px | `.imex-hero__badge`, `.imex-node__label` (base) |
| 12px | `.imex-tag`, `.imex-partner--muted`, footer bar |
| 12.5px | `.imex-fcard__text` |
| 13px | `.imex-lang__btn`, `.imex-step__desc`, `.imex-hero__trust`, footer links |
| 14px | `.imex-lh__link`, `.imex-lang__opt`, `.imex-partner` |
| 15px | `.imex-btn` (base), `.imex-hero__para`, `.imex-final__sub` |
| 16px | `.imex-btn--lg` |
| 18px | `.imex-footer__brand` |
| 22px | `.imex-feat__count` |
| 24px | `.imex-viz__core` "AI" |
| clamp(21px, 6vw, 26px) | `.imex-hero__title` |
| clamp(22px, 5.6vw, 26px) | `.imex-h2` |
| clamp(36px, 12vw, 46px) | `.imex-hero__wordmark` |

Distinct sizes: ~14 (excessive) but the range is justified by a complex marketing layout. The real concern is the bottom of the scale:

**WARNING — 10px node labels** (landing.css line 555, `@media (max-width: 560px)`): 10px text is below all practical readability standards. WCAG 2.1 does not specify a minimum size but 10px at mobile DPI is borderline. Combined with `color: #8B97A8` (passing AA contrast mathematically) and two-line wrapping of long Russian strings, these labels will be unreadable without zooming on most phones.

**WARNING — 12.5px sub-pixel size** (landing.css line 291, `.imex-fcard__text`): Sub-pixel font sizes render inconsistently across browsers. Round to 12px or 13px.

**WARNING — No fluid scaling below 560px for body text** (`.imex-hero__para` stays `font-size: 15px`; `.imex-step__desc` stays `13px`). The hero paragraph at 15px / line-length of full ~350px column is long (~70 characters per line) — approaching the upper bound for mobile comfort (~55–65 chars/line). Not critical but worth noting.

**What passes:** Font-weight discipline is good — 3 weights in practice (600 medium, 700 semibold, 800–900 heavy) applied hierarchically. `Inter` with `-apple-system` fallback is appropriate. `letter-spacing: -0.03em` on the wordmark, `-0.02em` on headings are intentional and brand-correct.

---

### Pillar 5: Spacing (2/4)

**What passes:**
- `padding-bottom: calc(72px + env(safe-area-inset-bottom))` on `.imex-landing` ensures the sticky bar does not clip content — base value.
- Panel padding `24px 16px` at ≤560px (down from `32px 22px`) is appropriate tightening.
- `gap: 10px` on hero feature cards grid is tight but legible at 2-col layout.

**Issues:**

**BLOCKER — Sticky bar vs footer legal bar** (landing.css lines 510–523, 494–506): The `.imex-sticky-cta` is `position: fixed; bottom: 0` with `padding: 10px 16px calc(10px + env(safe-area-inset-bottom))`. The `.imex-landing` bottom padding of `calc(72px + safe-area-inset-bottom)` at base and `calc(84px + safe-area-inset-bottom)` at ≤560px are meant to clear this. However, the footer sits outside `.imex-main` (it is a sibling element after `</main>`) and is a child of `.imex-landing`. The `padding-bottom` on `.imex-landing` should theoretically push the footer up. In practice, the `padding-bottom` override in the `@media (max-width: 560px)` block (line 559) correctly increases to `84px`, but this targets `.imex-landing`, not the footer element itself. Visual inspection of Screenshot 23.00.26 shows the sticky bar sitting over the "Купить / Продать" CTA buttons inside the partners section — this confirms overflow is occurring at that scroll position. The footer's own internal padding (`padding-top: 34px`, `imex-footer__bar` bottom `padding: 20px 0`) may be insufficient when the sticky bar height can reach ~70px + safe-area on iPhone models with home indicator.

**WARNING — `.imex-step__desc` max-width: 220px** (landing.css line 378): On a 390px viewport, a centered block with `max-width: 220px` leaves 85px of margin on each side. This is visually very narrow — approximately 30 characters per line in 13px Inter, causing most step descriptions to wrap to 4–5 lines. This makes the steps section feel very tall and vertically stretched. Increase to `max-width: 300px` or `max-width: 80%`.

**WARNING — `.imex-hero__grid { gap: 30px }` at mobile** (landing.css line 233): The single-column hero stack has a 30px gap between the text column and the globe visual. At ≤560px this drops to 20px. This is adequate but combined with the globe taking its full `300px` max-width, the complete hero section is very tall on mobile. Users must scroll significantly before seeing the value proposition below the globe. The globe could be reduced further or made collapsible on mobile.

**WARNING — Section gap rhythm inconsistency**: `.imex-section { padding: 26px 0 }` at ≤560px vs `.imex-hero { padding: 22px 0 10px }` creates a slightly uneven rhythm at the hero-to-how-it-works transition. Minor.

---

### Pillar 6: Experience Design (2/4)

**What passes:**
- Scroll reveal animation (`useScrollReveal` + `.reveal` class) has a `prefers-reduced-motion` override (landing.css line 529) — accessibility-correct.
- `CtaArt` component has an `onError` fallback to CSS barrels (Landing.tsx lines 293–315) — resilient.
- `PartnerTile` has `onError` fallback to brand name text (Landing.tsx lines 318–340) — resilient.
- `LangMenu` has a backdrop click-away dismiss (Landing.tsx line 358) — correct mobile interaction.
- `aria-haspopup="listbox"` and `aria-expanded` on the lang button (Landing.tsx line 353) — correct.
- `aria-hidden="true"` on the globe visual and arrow glyphs — correct (decorative).

**Issues:**

**BLOCKER — Five header nav items hidden with no mobile affordance** (landing.css line 110: `.imex-lh__nav { display: none }`): There is no hamburger, no drawer, no scroll-pill alternative. The sticky header on mobile shows only the brand wordmark and the language picker. On a 5-section landing page, discoverability of "Партнёры" and "Преимущества" sections depends entirely on scrolling. In the Telegram Mini App context, the swipe-from-left gesture is captured by Telegram's own navigation, so the page has no back-navigation gesture either. This is the most significant UX omission.

**WARNING — Triple identical CTA buttons** (Landing.tsx lines 131–136, 216–219, 232–237): "Купить сырьё" and "Продать сырьё" appear identically in three separate locations with no contextual differentiation. The hero placement, the final-CTA panel, and the sticky bar all fire the same `goBuy()` / `goSell()` functions. On desktop this is common (sticky header + hero + footer CTA), but on mobile where all three are simultaneously visible in different scroll positions, the user has no sense of progress or reward — the page feels like a one-screen repetition stretched to 5 sections.

**WARNING — Nav duplicate targets** (Landing.tsx lines 248–251): `about` and `how` both map to `id="how"`. If "О платформе" is expected to link to a brand story section, that section does not exist. If both are intentionally the same target, one of the nav items should be removed.

**WARNING — Footer action buttons non-functional** (Landing.tsx lines 511, 512, 518, 519): "FAQ", "Поддержка 24/7", "Политика конфиденциальности", "Условия использования" are `<button>` elements with no `onClick`. On mobile, tapping these produces no feedback — no toast, no navigation, no page link. This is a WCAG 2.1 criterion 4.1.2 failure (interactive elements must have a discernible result). At minimum, disable and visually indicate "coming soon", or wire to mailto/external links.

**WARNING — No loading state for the globe or landing images**: The Unsplash CTA image is loaded lazily and can take 1–3 seconds on mobile networks. There is no skeleton placeholder — the `imex-final__art` area collapses to `min-height: 150px` empty while loading. The partner logos fetched from Wikimedia Commons URLs (LUKOIL, SIBUR, KazMunayGas, NIOC) are external CDN fetches; on slow 3G or Telegram's proxied network, tiles will flash from text-fallback to logo. These are not blockers but reduce perceived performance quality.

**WARNING — Telegram Mini App context: safe-area-inset-bottom** (landing.css lines 33, 518, 559): `env(safe-area-inset-bottom)` is used correctly in the sticky CTA padding. However, Telegram Mini App also adds its own bottom chrome on some platforms. The `padding-bottom: calc(84px + env(safe-area-inset-bottom))` on `.imex-landing` for ≤560px may not account for the Mini App's internal safe-area override. `needs_human_review: true` — test on an actual iPhone 14+ device inside Telegram to confirm the footer is fully accessible.

---

## Files Audited

- `/Users/kholmumin/WebstormProjects/polymer-intelligence/webapp/src/pages/Landing.tsx`
- `/Users/kholmumin/WebstormProjects/polymer-intelligence/webapp/src/styles/landing.css`
- `/Users/kholmumin/WebstormProjects/polymer-intelligence/webapp/CLAUDE.md`
- `/Users/kholmumin/WebstormProjects/polymer-intelligence/webapp/src/i18n/ru.json` (landing namespace)
- Screenshots: docs/Screenshot 2026-07-03 at 22.58.44.png, 22.59.58.png, 23.00.12.png, 23.00.19.png, 23.00.26.png
