---
phase: 04-dashboard-source-constructor
plan: "03"
subsystem: dashboard-frontend
tags: [tanstack-table, tanstack-query, sse, live-feed, kpi-cards, ai-placeholder]
dependency_graph:
  requires: [04-01, 04-02]
  provides: [live-feed-table, feed-filters, kpi-card, status-chip, urgency-chip, kind-chip, ai-market-signals-panel, dashboard-home, signals-page, offers-page]
  affects: [04-04, 04-05, 04-06, 04-07, 04-08, 04-09]
tech_stack:
  added: []
  patterns:
    - "TanStack Table v8 + useQuery(['feed', filters]) + useSSE invalidation — live feed without page reload"
    - "Keyset pagination via next_cursor_event_at/next_cursor_id stack — no OFFSET"
    - "URL search params (useSearchParams + router.replace) for filter persistence across navigation"
    - "D-01 placeholder contract: final-shape panels with honest 'after Phase 5' text — no hidden sections"
    - "Suspense boundaries around useSearchParams client components in server page"
key_files:
  created:
    - dashboard/components/shared/StatusChip.tsx
    - dashboard/components/shared/UrgencyChip.tsx
    - dashboard/components/shared/KindChip.tsx
    - dashboard/components/shared/KpiCard.tsx
    - dashboard/components/feed/FeedFilters.tsx
    - dashboard/components/feed/LiveFeedTable.tsx
    - dashboard/components/feed/AiMarketSignalsPanel.tsx
    - dashboard/app/(dashboard)/signals/page.tsx
    - dashboard/app/(dashboard)/signals/NeedsReviewChip.tsx
    - dashboard/app/(dashboard)/offers/page.tsx
  modified:
    - dashboard/app/(dashboard)/page.tsx
decisions:
  - "DEC-04-03-suspense-boundaries: useSearchParams and useSSE hooks require 'use client'; server page.tsx wraps FeedFilters and LiveFeedTable in Suspense boundaries to allow server-side rendering of static KPI cards and panels"
  - "DEC-04-03-lucide-icon-type: UrgencyChip uses LucideIcon type (from lucide-react) for the Icon field in URGENCY_CONFIG — ComponentType<{size?, className?}> causes TS2322 because LucideProps.size is string|number, not just number"
  - "DEC-04-03-needs-review-chip-separate-file: NeedsReviewChip extracted to its own file to keep signals/page.tsx a Server Component while the chip uses useState for tooltip — avoids forcing the whole page to client"
metrics:
  duration: "~5 min"
  completed: "2026-06-17"
  tasks: 2
  files_created: 10
  files_modified: 1
---

# Phase 04 Plan 03: Live Market Feed Frontend Summary

TanStack-Table feed querying GET /feed with URL-persisted filters, SSE invalidation via useSSE, keyset pagination; shared StatusChip/UrgencyChip/KindChip/KpiCard using token classes only; Dashboard home with 5 KPI cards + D-01 AI panels; /signals + /offers pages.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Shared chips + KPI card + live feed table with SSE | 9157782 | StatusChip, UrgencyChip, KindChip, KpiCard, FeedFilters, LiveFeedTable |
| 2 | Dashboard home + AI signals panel + /signals + /offers pages | 00e73fb | AiMarketSignalsPanel, page.tsx (home), signals/page.tsx, offers/page.tsx |

## What Was Built

### Task 1: Shared Chips + KPI Card + Feed Table

**StatusChip:** Maps RequestStatus enum values to `text-status-* border-status-*` token classes. Label text + color (no color-alone accessibility). Supports all 7 statuses.

**UrgencyChip:** Icon + color per accessibility contract. High=Flame, Medium=Users, Low=Download (lucide-react). Uses `text-urgency-* border-urgency-*` token classes with `aria-label="Urgency: {level}"`.

**KindChip:** Maps buy_request/sell_offer/deal/price_quote/news to `text-kind-* border-kind-*` token classes with abbreviated labels (BUYER/SELLER/DEAL/PRICE/NEWS).

**KpiCard:** `icon (24px, foreground-muted)` + `label (12px font-semibold, foreground-muted)` + `value (28px font-semibold, foreground)` + optional `delta` chip with sentiment-driven color (positive=accent, neutral=status-new, negative=urgency-high).

**FeedFilters:** Period (7d/30d/90d), Kind, Source (text input), Urgency selects. All filter state persisted in URL search params via `useSearchParams` + `router.replace`. Supports `compact` mode for embedding in panels.

**LiveFeedTable:**
- `useQuery({ queryKey: ['feed', filters], queryFn })` calling `apiFetch('/feed?...')` with all 5 filter params + `limit=50`
- `useSSE('/api/v1/feed/stream', () => queryClient.invalidateQueries({ queryKey: ['feed'] }))` for live refresh without reload
- Keyset pagination: cursor stack (`useState`) tracks `{event_at, id}` pairs for Prev/Next navigation — no OFFSET
- All times wrapped in `<time datetime={iso}>` for screen reader accessibility
- Empty state: `Activity` icon + "No market activity yet" / "Signals will appear here as sources report data." per UI-SPEC copywriting contract
- T-04-08 (XSS): no `dangerouslySetInnerHTML`, all feed text rendered as React text nodes

### Task 2: Dashboard Home + AI Panel + Pages

**AiMarketSignalsPanel (D-01):** Final-shape panel with 3 placeholder rows — each: icon (TrendingUp/AlertTriangle/Bot) + "{label} — AI analysis available after Phase 5" (`text-foreground-subtle italic`). Amber "after Phase 5" badge in header. NOT a spinner, NOT a blank card.

**Dashboard Home (`page.tsx`):** Server component with:
- 5 KPI cards: Total Buyers (Users icon), Total Sellers (TrendingUp), Active Requests (FileText), Hot Leads (Flame — D-01: 0 value, "high priority" delta, rendered in final layout), Price Alerts (Bell)
- Live Market Feed panel with `<FeedFilters compact>` + `<LiveFeedTable compact>` in Suspense
- Price Trends placeholder panel with "View all" → /prices (wired Plan 04-08)
- AiMarketSignalsPanel
- Top Buyer Requests + Top Seller Offers placeholder panels

**Signals page (`/signals`):** Full-page `LiveFeedTable` + `FeedFilters` + disabled `NeedsReviewChip` with tooltip "Available after Phase 5 AI" (per UI-SPEC).

**Offers page (`/offers`):** `LiveFeedTable defaultKind="sell_offer"` — pre-filtered to sell offers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] UrgencyChip Icon type — LucideProps.size is string|number, not number**
- **Found during:** Task 1 typecheck
- **Issue:** `ComponentType<{ size?: number; className?: string }>` caused TS2322 — `LucideProps.size` is `string | number | null | undefined` but the inline type expected `number | null | undefined`.
- **Fix:** Changed the `Icon` field type in `URGENCY_CONFIG` to `LucideIcon` (imported from `lucide-react`), which is the correct ForwardRefExoticComponent type for all lucide icons.
- **Files modified:** `dashboard/components/shared/UrgencyChip.tsx`
- **Commit:** 9157782 (fixed before commit, same task)

**2. [Rule 3 - Blocking] Suspense required for useSearchParams in server pages**
- **Found during:** Task 2 (build verification)
- **Issue:** Next.js App Router requires `useSearchParams` to be used inside a client component that is wrapped in `<Suspense>` when called from a server component page. Without Suspense, the build would error or the page would not prerender.
- **Fix:** Added `<Suspense fallback={null}>` around `<FeedFilters>` and `<Suspense fallback={<FeedLoadingFallback />}>` around `<LiveFeedTable>` in all three page files.
- **Files modified:** `page.tsx`, `signals/page.tsx`, `offers/page.tsx`
- **Commit:** 00e73fb (applied during Task 2 implementation)

**None additional** — plan executed with 2 auto-fixes, no architectural changes.

## Verification Results

All acceptance criteria passed:

**Task 1:**
- `dashboard/components/feed/LiveFeedTable.tsx` contains `['feed'` query key, `useSSE`, and `feed/stream`
- `grep -rE "#[0-9a-fA-F]{6}" dashboard/components/shared/ dashboard/components/feed/` — returns nothing (no hardcoded hex)
- `UrgencyChip.tsx` imports Flame, Users, Download from lucide-react; renders `<Icon>` with aria-label
- `npm run typecheck` — exit 0
- `npm run lint` — exit 0 (1 warning: TanStack Table useReactTable incompatible-library — expected, not an error)

**Task 2:**
- `AiMarketSignalsPanel.tsx` contains "after Phase 5" and renders 3 placeholder rows with icons
- `app/(dashboard)/page.tsx` imports and renders `KpiCard` and `LiveFeedTable`, contains Hot Leads KPI in final layout
- `/offers` page applies `defaultKind="sell_offer"`; `/signals` page renders `NeedsReviewChip` with Phase 5 tooltip
- `npm run typecheck` — exit 0
- `npm run lint` — exit 0
- `npm run build` — completes with 5 routes (/, /_not-found, /login, /offers, /signals)

## Known Stubs

The following stubs are intentional per the D-01 placeholder contract:

| Stub | File | Reason |
|------|------|--------|
| KPI values "—" for Total Buyers/Sellers/Active Requests/Price Alerts | `app/(dashboard)/page.tsx` | Phase 4 has no `/kpi` endpoint yet — Plan 04-04+ wires individual screen KPIs. Home KPIs will be wired in a later plan. |
| Hot Leads KPI value = 0 | `app/(dashboard)/page.tsx` | Intentional D-01 — `lead_score` column is null in Phase 4; Phase 5 fills it. Final layout already rendered. |
| AiMarketSignalsPanel rows show placeholder text | `AiMarketSignalsPanel.tsx` | Intentional D-01 — AI analysis wired in Phase 5. Final panel shape ready. |
| Price Trends panel shows placeholder | `app/(dashboard)/page.tsx` | Wired in Plan 04-08 (Price Trends chart). |
| Top Buyer/Seller panels show placeholder | `app/(dashboard)/page.tsx` | Wired in Plans 04-04/04-05. |

All stubs are by design and do not prevent the plan goal (REQ-live-feed frontend end-to-end): the feed table queries /feed, refreshes via SSE, filters persist in URL, chips use token classes, AI surfaces are final-shaped.

## Threat Surface Scan

No new security surface beyond the plan's threat model:

- T-04-08 (XSS): mitigated — no `dangerouslySetInnerHTML` anywhere in created files; all feed row data rendered as React text nodes (escaped by default)
- T-04-09 (Info Disclosure): accepted — UI renders only what the JWT-guarded /feed API returns; no client-side filtering bypass
- T-04-SC (npm): no new packages installed — all deps from 04-02 (TanStack Table/Query, lucide-react, next/navigation already present)

## Self-Check

Checking created files exist:
- FOUND: dashboard/components/shared/StatusChip.tsx
- FOUND: dashboard/components/shared/UrgencyChip.tsx
- FOUND: dashboard/components/shared/KindChip.tsx
- FOUND: dashboard/components/shared/KpiCard.tsx
- FOUND: dashboard/components/feed/FeedFilters.tsx
- FOUND: dashboard/components/feed/LiveFeedTable.tsx
- FOUND: dashboard/components/feed/AiMarketSignalsPanel.tsx
- FOUND: dashboard/app/(dashboard)/signals/page.tsx
- FOUND: dashboard/app/(dashboard)/signals/NeedsReviewChip.tsx
- FOUND: dashboard/app/(dashboard)/offers/page.tsx
- FOUND: dashboard/app/(dashboard)/page.tsx (modified)

Checking commits exist:
- FOUND: 9157782 (Task 1)
- FOUND: 00e73fb (Task 2)

## Self-Check: PASSED
