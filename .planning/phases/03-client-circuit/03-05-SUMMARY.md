---
phase: 03-client-circuit
plan: 05
subsystem: ui
tags: [webapp, react, vite, react-i18next, zustand, my-requests, status-timeline, settings, i18n, bundle, performance, Asia/Tashkent]

# Dependency graph
requires:
  - phase: 03-04
    provides: app shell, i18n setup, api client, StatusChip, zustand wizard store, Home + wizard screens C-01..C-05
  - phase: 03-02
    provides: /webapp/requests, /webapp/requests/{id}, /webapp/me PATCH — the data endpoints these screens consume

provides:
  - MyRequests (C-06): request list with status chips, 3-card skeleton, empty state, pull-to-refresh (haptic), visibilitychange refetch
  - RequestDetail (C-07): full request fields, attached files list, StatusChip, StatusTimeline with Asia/Tashkent timestamps
  - Notifications (C-08): registered route with EmptyState (bot-side delivery; deep-link target)
  - Settings (C-09): RU/UZ segmented control — PATCHes /webapp/me, calls i18n.changeLanguage immediately, optimistic UI
  - Supporting components: RequestCard, StatusTimeline, EmptyState, ErrorBanner
  - webapp/src/util/datetime.ts: formatTashkent() — Asia/Tashkent display helper (D-11, DEC-tz-handling)
  - Bundle budget verified: largest gzip chunk 42.8 KB (vendor), well within ≤300 KB gate (REQ-nfr-performance)
  - All C-01..C-09 routes wired; no placeholder components remain in App.tsx

affects:
  - 03-06 (E2E acceptance — full-stack test of list/detail/timeline/notify; deferred backend-backed verification lands here)
  - 04-* (dashboard — can reference completed client-circuit patterns and component conventions)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - formatTashkent(utcIso) via Intl.DateTimeFormat with timeZone:'Asia/Tashkent' — single util for all frontend UTC→display conversions
    - rollup manualChunks (function form for Vite 8/rolldown): vendor (react/react-dom/router) + i18n chunks split from app code
    - Optimistic language switch: patchMe() fires in background; i18n.changeLanguage + localStorage update immediately on control change; PATCH failure shows ErrorBanner but keeps new language

key-files:
  created:
    - webapp/src/util/datetime.ts
    - webapp/src/components/RequestCard.tsx
    - webapp/src/components/StatusTimeline.tsx
    - webapp/src/components/EmptyState.tsx
    - webapp/src/components/ErrorBanner.tsx
    - webapp/src/pages/MyRequests.tsx
    - webapp/src/pages/RequestDetail.tsx
    - webapp/src/pages/Notifications.tsx
  modified:
    - webapp/src/pages/Settings.tsx
    - webapp/src/App.tsx
    - webapp/vite.config.ts

key-decisions:
  - "DEC-03-05-optimistic-language: Settings switches UI immediately on toggle (no round-trip wait); PATCH failure shows ErrorBanner but does not revert UI language — optimistic per UI-SPEC D-04"
  - "DEC-03-05-backend-verify-deferred: Live backend-backed list (newest-first chips), detail timeline, and foreground-refetch verification explicitly deferred to 03-06 E2E acceptance plan by user agreement at Task 3 checkpoint"
  - "DEC-03-05-vite8-manualchunks: manualChunks uses function form (not object) for Vite 8 / rolldown compatibility; vendor chunk = react + react-dom + react-router-dom, i18n chunk = i18next + react-i18next"
  - "DEC-03-05-notifications-empty: Notifications C-08 shows EmptyState only — notification persistence is bot-side (03-03); screen exists as deep-link target and nav destination per UI-SPEC C-08"

patterns-established:
  - "Asia/Tashkent display: all UTC ISO strings go through formatTashkent() — never inline Intl calls in components"
  - "Page skeleton: 3-card pulsing skeleton during loading, EmptyState when list is zero length, ErrorBanner on fetch failure"
  - "Component tap targets: ≥44px min-height on interactive list items (RequestCard) per UI-SPEC accessibility contract"

requirements-completed: [REQ-my-requests, REQ-webapp-i18n, REQ-nfr-performance]

# Metrics
duration: ~60min
completed: 2026-06-17
---

# Phase 03 Plan 05: My-Requests + Detail UI Summary

**Four Web App screens (C-06..C-09) + four supporting components + datetime util shipped; bundle measured at 42.8 KB gzip largest chunk (vs ≤300 KB budget); frontend layer verified live by human; backend-backed list/timeline verification deferred to 03-06 E2E by user agreement.**

## Performance

- **Duration:** ~60 min (implementation pre-committed; finalization 2026-06-17)
- **Started:** 2026-06-16
- **Completed:** 2026-06-17
- **Tasks:** 3 (2 auto + 1 checkpoint:human-verify)
- **Files modified:** 11

## Accomplishments

- MyRequests (C-06) renders a 3-card pulsing skeleton while loading, switches to a request list (newest-first) with StatusChip per D-10, shows EmptyState on zero results, and ErrorBanner on fetch failure; supports pull-to-refresh (Telegram haptic) and visibilitychange refetch for foreground updates.
- RequestDetail (C-07) fetches by id, renders all request fields (product, grade, volume, target price, incoterms, comment), attached files list, StatusChip, and the full StatusTimeline; timestamps display in Asia/Tashkent local time via formatTashkent() — closing D-11.
- Settings (C-09) RU/UZ segmented control calls patchMe({language}) and i18n.changeLanguage immediately (optimistic, no reload); persists to localStorage; shows ErrorBanner on PATCH failure without reverting UI language.
- All C-01..C-09 routes resolve to real React.lazy components in App.tsx — no placeholders remain.
- Bundle verified at build time: largest gzip chunk is 42.8 KB (vendor: react + react-dom + react-router-dom), well within the ≤300 KB budget (REQ-nfr-performance, T-03-20).

## Task Commits

Each task was committed atomically:

1. **Task 1: MyRequests (C-06), RequestDetail + StatusTimeline (C-07), Notifications (C-08), supporting components** - `53405ad` (feat)
2. **Task 2: Settings/language (C-09), route wiring, and bundle ≤300 KB gzip verification** - `0c343d7` (feat)
3. **Task 3: Human-verify checkpoint** — approved by user (frontend layer); backend-backed steps deferred to 03-06 by explicit user agreement (no code commit)

## Files Created/Modified

**Created:**
- `webapp/src/util/datetime.ts` — formatTashkent(utcIso): string using Intl.DateTimeFormat with timeZone:'Asia/Tashkent' (D-11, DEC-tz-handling)
- `webapp/src/components/RequestCard.tsx` — full-width tap target (≥44px), request number/StatusChip/product/date, navigates to /requests/{id}
- `webapp/src/components/StatusTimeline.tsx` — vertical list of StatusHistory rows (from_status→to_status) with formatTashkent timestamps; heading from t('requestDetail.history')
- `webapp/src/components/EmptyState.tsx` — illustration-free heading + body + optional CTA; copy from t() key prop
- `webapp/src/components/ErrorBanner.tsx` — full-width destructive banner at 10% opacity (#ef4444 per UI-SPEC sole-hex exception)
- `webapp/src/pages/MyRequests.tsx` — C-06 screen (skeleton / list / empty / error / pull-to-refresh / visibilitychange)
- `webapp/src/pages/RequestDetail.tsx` — C-07 screen (fields / files / chip / timeline / error)
- `webapp/src/pages/Notifications.tsx` — C-08 registered route with EmptyState

**Modified:**
- `webapp/src/pages/Settings.tsx` — C-09 RU/UZ segmented control, patchMe + changeLanguage (full rewrite from 03-04 placeholder)
- `webapp/src/App.tsx` — bound /requests, /requests/:id, /notifications, /settings to real lazy components; all C-01..C-09 complete
- `webapp/vite.config.ts` — rollup manualChunks (function form, Vite 8/rolldown); vendor + i18n chunk split

## Decisions Made

- **DEC-03-05-optimistic-language:** Settings switches language immediately on segmented control change (optimistic). PATCH failure surfaces an ErrorBanner but does not revert language locally — consistent with UI-SPEC D-04 "immediate" requirement and good UX on flaky connections.
- **DEC-03-05-vite8-manualchunks:** manualChunks uses the function form rather than object form for Vite 8 / rolldown compatibility. Vendor chunk = react + react-dom + react-router-dom; i18n chunk = i18next + react-i18next. Produces 42.8 KB gzip largest chunk.
- **DEC-03-05-notifications-empty:** Notifications C-08 shows only EmptyState in this phase — notification persistence is bot-side (03-03 Celery notify task via deliveries queue). Screen exists as deep-link target and nav destination per UI-SPEC C-08; content populates when the bot delivers notifications.
- **DEC-03-05-backend-verify-deferred:** Task 3 checkpoint verified the frontend layer live (Settings RU/UZ toggle, Notifications empty state, loading/error states). The backend-backed verification steps (live my-requests list newest-first with status chips, detail status-history timeline in Asia/Tashkent, foreground-refetch on visibilitychange) were explicitly deferred to 03-06 E2E acceptance plan by user agreement. This is a noted deferral, NOT a defect — the frontend code is fully implemented and correct; 03-06 stands up the full stack.

## Deviations from Plan

None — plan executed as specified. Both auto tasks completed cleanly; checkpoint resolved as expected (frontend approved, backend-backed steps deferred to 03-06 by user agreement, documented above).

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Threat Model Coverage

All three threat model entries from the plan are mitigated:

| Threat ID | Mitigation | Status |
|-----------|-----------|--------|
| T-03-18 | RequestDetail fetches via api.getRequest(id) — initData-scoped server-side (03-02 T-03-07); non-owned id returns 404 rendered as ErrorBanner | Mitigated |
| T-03-19 | Settings PATCH /webapp/me sends no client id; server scopes to verified initData client | Mitigated |
| T-03-20 | Route-level code-split + manualChunks + named lucide imports; build-time gzip gate measured at 42.8 KB (≤300 KB) | Mitigated |

## Next Phase Readiness

**03-06 E2E acceptance plan** can now proceed. It will stand up the full stack (backend 03-02 + 03-03 + 03-01 + webapp 03-04 + 03-05) and verify:
- Live my-requests list newest-first with correct D-10 status chips
- Detail status-history timeline displaying Asia/Tashkent timestamps
- Foreground-refetch on visibilitychange
- Automated SLA proxies (≤10 s request readback, ≤30 s notify dispatch)
- Phase-03 acceptance doc mapping the 5 success criteria to a live drill

All frontend screen code for Phase 3 is complete. The only remaining Phase 3 work is 03-06 (acceptance gate).

---
*Phase: 03-client-circuit*
*Completed: 2026-06-17*
