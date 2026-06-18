---
phase: 04-dashboard-source-constructor
plan: "08"
subsystem: dashboard-frontend
tags: [nextjs, react, recharts, tanstack-query, shadcn, no-code-wizard, jsonschema, alerts, price-chart]

# Dependency graph
dependency_graph:
  requires:
    - phase: 04-02
      provides: api.ts, apiFetch, useAuth, queryClient, AppShell, token classes
    - phase: 04-03
      provides: StatusChip, UrgencyChip, KpiCard, shared components
    - phase: 04-05
      provides: page patterns, useMutation+invalidate, Sheet pattern
    - phase: 04-06
      provides: GET/POST/PATCH /sources + POST /sources/{id}/test + SourceHealthItem schema
    - phase: 04-07
      provides: GET/POST/PATCH /alert-rules + GET /alerts + GET /prices/series + schemas
  provides:
    - "JsonSchemaForm: auto-form renderer from Pydantic v2 JSON schema (anyOf unwrap for Optional)"
    - "AddSourceWizard: 4-step dialog (pick/configure/test/enable) with pending pre-staging"
    - "SourcesList: health table with pending badge + disabled Test/Enable for Phase-5 types"
    - "AlertFeed: triggered alerts table with severity chips"
    - "RuleBuilder: full predicate form (lead_score disabled), per-rule chat_id textarea"
    - "PriceChart: Recharts LineChart from /prices/series with SERIES_COLORS"
    - "app/(dashboard)/sources/page.tsx: sources list + wizard entry point"
    - "app/(dashboard)/alerts/page.tsx: alert feed + rule builder"
    - "app/(dashboard)/prices/page.tsx: product tabs + market/date/currency controls + chart"
    - "app/(dashboard)/admin/users/page.tsx: role-gated staff user table"
  affects: [04-09-acceptance]

# Tech tracking
tech-stack:
  added: []  # No new packages — recharts/shadcn/tanstack already installed
  patterns:
    - "JsonSchemaForm resolveType: anyOf:[T,null] → T (Pydantic Optional unwrap, Pitfall 4)"
    - "JsonSchemaForm mirrors required[] from schema.required array client-side"
    - "SERIES_COLORS hex map (Recharts stroke exception — CSS vars not supported in SVG props)"
    - "Pending adapter guard: PENDING_ADAPTERS = Set(['telegram_channel','llm_page'])"
    - "TooltipTrigger render= prop (base-ui/react Tooltip API, not Radix asChild)"
    - "admin/users page: useEffect redirect for non-admin (UI gate, backend enforces)"

key-files:
  created:
    - dashboard/components/sources/JsonSchemaForm.tsx
    - dashboard/components/sources/AddSourceWizard.tsx
    - dashboard/components/sources/SourcesList.tsx
    - dashboard/components/alerts/AlertFeed.tsx
    - dashboard/components/alerts/RuleBuilder.tsx
    - dashboard/components/prices/PriceChart.tsx
    - dashboard/app/(dashboard)/sources/page.tsx
    - dashboard/app/(dashboard)/alerts/page.tsx
    - dashboard/app/(dashboard)/prices/page.tsx
    - dashboard/app/(dashboard)/admin/users/page.tsx
  modified: []

key-decisions:
  - "DEC-04-08-base-ui-tooltip-render: base-ui/react Tooltip.Trigger uses render= prop (not Radix asChild); TooltipTrigger asChild={true} is not supported by @base-ui/react — fixed by Rule 1"
  - "DEC-04-08-series-colors-hex-only: SERIES_COLORS hex values placed in Recharts stroke props only — Recharts cannot use CSS custom properties (not resolved on SVG canvas). Each value comments the corresponding tailwind.config.ts token."
  - "DEC-04-08-pending-adapter-set: PENDING_ADAPTERS = Set(['telegram_channel','llm_page']) — pending check is centralized in a module-level Set so adding Phase-5 adapters is one-line change."
  - "DEC-04-08-admin-users-ui-redirect: Admin Users page uses useEffect to redirect non-admin to /. Backend require_admin is the real security gate; UI redirect is UX-only per threat model T-04-30."

# Metrics
duration: ~10 min
completed: 2026-06-18
---

# Phase 04 Plan 08: Surface-B Feature Screens Summary

**JsonSchemaForm + AddSourceWizard + SourcesList + AlertFeed + RuleBuilder + PriceChart + sources/alerts/prices/admin-users pages — typecheck exit 0, lint 0 errors, build 11 routes all static**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-18T07:23:46Z
- **Completed:** 2026-06-18T07:34:12Z
- **Tasks:** 3
- **Files created:** 10
- **Files modified:** 0

## Accomplishments

### Task 1: JsonSchemaForm + AddSourceWizard + SourcesList + sources page

**JsonSchemaForm** (`components/sources/JsonSchemaForm.tsx`):
- Auto-renders form fields from a Pydantic v2 JSON Schema: string text, `format=uri` url (SSRF hint "Public URLs only."), integer/number, enum → `<select>`, boolean → checkbox
- `resolveType()` unwraps `anyOf:[T, null]` → T for Pydantic `Optional[X]` fields (RESEARCH Pitfall 4)
- `required[]` array mirrored client-side — asterisk on required labels, validation on submit
- No hardcoded hex; all styles via Tailwind token classes

**AddSourceWizard** (`components/sources/AddSourceWizard.tsx`):
- shadcn `Dialog` (max-width 560px, `bg-background-secondary rounded-xl`), 4-step numbered indicator
- Step 1: 2×2 radio card grid (HTML Table, RSS Feed, Telegram Channel [Phase 5 badge], LLM Page [Phase 5 badge]) — pending types selectable with warning banner (D-05)
- Step 2: Source name input + `JsonSchemaForm` from `GET /admin/source-types`; pending types jump to step 4 (Save as Pending) without test
- Step 3 (html_table/rss only): Run Test → `POST /sources` then `POST /sources/{id}/test` → ≤10-row preview table (product/grade/volume/price/currency/section/event_at D-06) or failure banner
- Step 4: "Enable Source" (accent, only active if test passed) / "Save as Pending" (outline); `PATCH /sources/{id} is_enabled=true` if enabling

**SourcesList** (`components/sources/SourcesList.tsx`):
- Health table per source: Name, Type badge, Status chip (enabled/disabled), Last Fetch (Asia/Tashkent), Consecutive Failures (urgency-high red if >0)
- Pending types (telegram_channel/llm_page with `last_test_ok_at=null`): amber "Pending activation (Phase 5)" badge, Test/Enable disabled with "Available after Phase 5" tooltip (D-05)
- Enable/Disable toggle: `PATCH /sources/{id}`; Disable shows AlertDialog confirm copywriting
- Inline test result banner after clicking Test

**sources/page.tsx**: Page header + "Add Source" accent button + SourcesList + empty state ("No sources configured")

### Task 2: AlertFeed + RuleBuilder + alerts page

**AlertFeed** (`components/alerts/AlertFeed.tsx`):
- `useQuery(['alerts'])` → `GET /alerts` table newest-first
- Severity chips: info=`text-status-new` (blue), warning=`text-urgency-medium` (amber), critical=`text-urgency-high` (red) — no hardcoded hex
- Empty state: Bell icon + "No alerts triggered yet" / "Configure a rule to start receiving alerts."

**RuleBuilder** (`components/alerts/RuleBuilder.tsx`):
- Full predicate form: name (required), kind multiselect chips, product select, volume >= number, urgency checkboxes (high/medium/low), source-kind multiselect
- Lead Score >= (D-07): rendered DISABLED with amber label "Activates with Phase 5 AI" + tooltip "Available after Phase 5"; input is `disabled` + `cursor-not-allowed opacity-50`
- Delivery chat_id textarea (D-08): one per line, help text per UI-SPEC, builds `channels: [{type, chat_id}]` array
- Urgency channel select (DM/Group)
- Save → `POST /alert-rules` with built condition + channels; `useMutation + invalidateQueries`
- Existing rules list: name + predicate summary + delivery count + delete (AlertDialog confirm "Delete this rule? Active deliveries using this rule will stop immediately.")
- Write actions (Create Rule, Delete Rule) hidden for non-admin (`isAdmin` prop from `useAuth().role`)

**alerts/page.tsx**: AlertFeed + RuleBuilder sections; role-gated write UI

### Task 3: PriceChart + prices page + admin users page

**PriceChart** (`components/prices/PriceChart.tsx`):
- Recharts `LineChart` in `ResponsiveContainer` (100% × 400px)
- `useQuery(['prices','series', filters])` → `GET /prices/series?...`
- `SERIES_COLORS` hex map — the ONLY exception to no-hardcoded-hex rule; Recharts stroke props cannot use CSS variables (SVG canvas); each value comments the tailwind.config.ts token it matches
- Grid stroke = `#1e293b` (border-subtle), axis text fill = `#94a3b8` (foreground-muted), both in comment-documented hex-only Recharts props
- USD/UZS on-read FX conversion via `fxRate` prop
- Loading/error/empty states

**prices/page.tsx**:
- Product pill tabs (PP Raffia/HDPE/LDPE/LLDPE/PVC/PET/PS/ABS)
- Market select (UZEX/CBU/All)
- Date presets 7d/30d/90d + custom date range pickers
- Currency toggle USD/UZS

**admin/users/page.tsx**:
- `GET /admin/users` table: email, role badge (admin=accent/analyst=text-status-new/trader=urgency-medium/viewer=foreground-muted), is_active status, created_at
- No password_hash in interface or rendering (T-04-32)
- `useEffect` redirect for non-admin to `/` (UI gate; backend `require_admin` is the security boundary)

## Task Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | JsonSchemaForm + AddSourceWizard + SourcesList + sources page | 1622bfa | 4 files created |
| 2 | AlertFeed + RuleBuilder + alerts page | 200bc0a | 3 files created |
| 3 | PriceChart + prices page + admin users page | cd9e813 | 3 files created |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TooltipTrigger `asChild` prop not supported by @base-ui/react**
- **Found during:** Task 1 typecheck
- **Issue:** `<TooltipTrigger asChild>` pattern from Radix UI is not valid in @base-ui/react (the installed tooltip library). TypeScript error: "Property 'asChild' does not exist on type 'IntrinsicAttributes & Props<unknown>'".
- **Fix:** Changed to `<TooltipTrigger render={<button ...>...</button>} />` which is the @base-ui/react API for rendering the trigger as a custom element.
- **Files modified:** `dashboard/components/sources/SourcesList.tsx`
- **Commit:** 1622bfa

**2. [Rule 1 - Bug] Duplicate `configValues` state after edit**
- **Found during:** Task 1 lint — `'configValues' is assigned a value but never used`
- **Issue:** Manual edit accidentally created a duplicate state declaration (`[configValues, setConfigValues]` declared twice). The values are passed directly to `mutateAsync`, so the tracking state is not needed.
- **Fix:** Removed the redundant state declaration and all `setConfigValues(values)` calls.
- **Files modified:** `dashboard/components/sources/AddSourceWizard.tsx`
- **Commit:** 1622bfa

**3. [Rule 1 - Bug] `type { RuleFormState }` syntax error at bottom of RuleBuilder**
- **Found during:** Task 2 typecheck — "Type alias name cannot be 'type'"
- **Issue:** Used `type { RuleFormState }` (invalid standalone export syntax) instead of `export type { RuleFormState }`.
- **Fix:** Changed to `export type { RuleFormState }`.
- **Files modified:** `dashboard/components/alerts/RuleBuilder.tsx`
- **Commit:** 200bc0a

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| Lead Score >= input always disabled | `RuleBuilder.tsx` | D-07: authored for future Phase 5 activation; correct by design — predicate interpreter never matches in Phase 4 |
| telegram_channel/llm_page Test/Enable disabled | `SourcesList.tsx`, `AddSourceWizard.tsx` | D-05: pending stub; correct by design — adapters return `TestResult(ok=False)` until Phase 5 |
| PriceChart fxRate defaults to 1 (no FX endpoint call) | `PriceChart.tsx` | No `/fx-rates` endpoint exists in Phase 4; UZS conversion passes through at 1:1 until FX data is wired |

All stubs are intentional per D-04/D-05/D-07 and do not prevent the plan goal.

## Threat Surface Scan

All threat model mitigations from the plan verified:

| Threat | Status |
|--------|--------|
| T-04-29 XSS (preview rows, alert messages) | Mitigated — all text rendered as React nodes; no `dangerouslySetInnerHTML` |
| T-04-30 Elevation (wizard/rules/admin write actions) | Mitigated — UI hides write actions for non-admin; backend `require_admin` is the enforced boundary |
| T-04-31 Enable bypass (wizard Enable button) | Mitigated — UI disables Enable until `testResult.ok`; backend PATCH enforces `last_test_ok_at IS NOT NULL` |
| T-04-32 Info Disclosure (admin users screen) | Mitigated — `StaffUserItem` interface has no `password_hash`; page admin-only with redirect |

No new trust boundaries introduced beyond those in the plan's threat model.

## Self-Check: PASSED

Files confirmed on disk:
- FOUND: dashboard/components/sources/JsonSchemaForm.tsx
- FOUND: dashboard/components/sources/AddSourceWizard.tsx
- FOUND: dashboard/components/sources/SourcesList.tsx
- FOUND: dashboard/components/alerts/AlertFeed.tsx
- FOUND: dashboard/components/alerts/RuleBuilder.tsx
- FOUND: dashboard/components/prices/PriceChart.tsx
- FOUND: dashboard/app/(dashboard)/sources/page.tsx
- FOUND: dashboard/app/(dashboard)/alerts/page.tsx
- FOUND: dashboard/app/(dashboard)/prices/page.tsx
- FOUND: dashboard/app/(dashboard)/admin/users/page.tsx

Commits verified in git log:
- FOUND: 1622bfa (Task 1: JsonSchemaForm + AddSourceWizard + SourcesList + sources page)
- FOUND: 200bc0a (Task 2: AlertFeed + RuleBuilder + alerts page)
- FOUND: cd9e813 (Task 3: PriceChart + prices page + admin users page)

Build verified: 11 routes all static (npm run build exit 0)
Typecheck verified: tsc --noEmit exit 0
Lint verified: 0 errors, 2 pre-existing warnings (TanStack Table incompatible-library from prior plans)
