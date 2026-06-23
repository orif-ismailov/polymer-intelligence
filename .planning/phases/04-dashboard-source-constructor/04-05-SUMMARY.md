---
phase: 04-dashboard-source-constructor
plan: "05"
subsystem: purchase-requests-frontend
tags: [tanstack-table, tanstack-query, shadcn-sheet, csv-export, d01-ai-placeholder, d02-price-analysis, d10-audit, d11-contact-buyer, d12-status-machine]

# Dependency graph
dependency_graph:
  requires:
    - phase: 04-02
      provides: api.ts, apiFetch, hooks, AppShell, queryClient, token classes
    - phase: 04-03
      provides: StatusChip, UrgencyChip, KpiCard, shared components
    - phase: 04-04
      provides: GET/PATCH /requests, POST note/assign/contact, GET /admin/users, RequestDetailOut schema
  provides:
    - "RequestsTable: TanStack Table 10-row paginated, sortable, row-click ?id= param"
    - "RequestsFilterBar: period/urgency/status selects + removable chips + clear"
    - "ExportCsvButton: GET /requests/export with current URL filters"
    - "RequestDetailPanel: 400px shadcn Sheet side=right, role=dialog, useQuery(['request', id])"
    - "AiAnalysisBlock: D-01 Match Score placeholder + D-02 real price analysis"
    - "RequestActions: Contact Buyer (D-11), Add Note, Status dropdown, Assign Owner, Mark as Processed (D-10/D-12)"
    - "GET /api/v1/requests/export: CSV StreamingResponse, 50k cap, content-disposition attachment"
    - "app/(dashboard)/requests/page.tsx: flagship master-detail page"
  affects: [04-09-acceptance]

# Tech tracking
tech_stack:
  added: []
  patterns:
    - "useQuery(['requests', filters]) + URL search params persistence for filter state"
    - "TanStack Table getPaginationRowModel, getSortedRowModel for client-side 10-row pages + sort"
    - "shadcn Sheet side=right as 400px detail panel; opened/closed via URL ?id= param"
    - "useMutation + invalidateQueries(['request', id]) + ['requests'] pattern for all D-10 actions"
    - "D-11 Pitfall 6 guard: Contact Buyer disabled + tooltip when contact_available=false"
    - "StreamingResponse + csv.writer generator for GET /requests/export (T-04-18: 50k cap)"
    - "page.tsx 'use client' directive required when Lucide icon components passed as props to KpiCard"

key_files:
  created:
    - dashboard/components/requests/RequestsTable.tsx
    - dashboard/components/requests/RequestsFilterBar.tsx
    - dashboard/components/requests/ExportCsvButton.tsx
    - dashboard/components/requests/RequestDetailPanel.tsx
    - dashboard/components/requests/AiAnalysisBlock.tsx
    - dashboard/components/requests/RequestActions.tsx
    - dashboard/app/(dashboard)/requests/page.tsx
    - backend/tests/test_requests_export.py
  modified:
    - backend/app/api/dashboard_requests.py

key-decisions:
  - "DEC-04-05-page-use-client: requests/page.tsx uses 'use client' because Lucide icon components cannot be passed as function props from Server Components to Client Components (Next.js App Router constraint). All Suspense boundaries still work from a client page."
  - "DEC-04-05-kpi-stubs: The 6 KPI cards on /requests all show '—' — no aggregate KPI endpoint exists for /requests in Phase 4 (only individual request data). These are D-01-pattern stubs per the placeholder contract; the final card shapes are rendered."
  - "DEC-04-05-region-source-stubs: Region and Source columns in RequestsTable return '—' — these fields are not in RequestListOut schema from 04-04. The column structure is correct per UI-SPEC; data wiring deferred to a schema extension."

metrics:
  duration: "~15 min"
  completed: "2026-06-17"
  tasks: 3
  files_created: 8
  files_modified: 1
---

# Phase 04 Plan 05: Purchase Requests Frontend Summary

Flagship master-detail frontend for REQ-purchase-requests: paginated TanStack Table with filter bar + KPI cards, 400px shadcn Sheet detail panel with Request Details / Source Information / AI Analysis / Files / Actions, all D-10 team actions (Contact Buyer, Add Note, Status dropdown, Assign Owner, Mark as Processed) wired to backend, CSV export streaming endpoint added to backend, AI block with D-01 placeholders + D-02 real price analysis.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Backend GET /requests/export CSV stream + test | 5a522e9 | dashboard_requests.py (+export route), test_requests_export.py (6 tests) |
| 2 | Requests table + filter bar + KPI cards + requests page | dc2c1a1 | RequestsTable.tsx, RequestsFilterBar.tsx, ExportCsvButton.tsx, requests/page.tsx |
| 3 | Detail Sheet + AI block (D-01/D-02) + actions (D-10/D-11/D-12) | 8d80a7c | RequestDetailPanel.tsx, AiAnalysisBlock.tsx, RequestActions.tsx, page.tsx (use client fix) |

## What Was Built

### Task 1: Backend CSV Export Endpoint

`GET /api/v1/requests/export` added to `dashboard_requests.py` (extending the 04-04 router):
- `StreamingResponse` with `csv.writer` generator — yields header row then data rows one-by-one
- Accepts same filter query params as `GET /requests` (`status`, `urgency`, `product_id`)
- Capped at 50,000 rows via `.limit(_EXPORT_ROW_CAP)` (T-04-18: avoids loading full result into memory)
- `Content-Disposition: attachment; filename=requests.csv`
- Guarded by `get_current_staff_user` (any staff role)
- Route defined BEFORE `/{request_id}` to avoid the `/export` path being captured as an ID

`test_requests_export.py` — 6 tests covering:
- `text/csv` content-type
- `attachment; filename=requests.csv` Content-Disposition
- Header row presence with `id`, `number`, `status` columns
- Data row presence given mocked result set
- Empty result returns only header row
- 401 without Bearer token

### Task 2: Requests Table + Filter Bar + KPI Cards + Page

**RequestsTable** (`"use client"`):
- `useQuery(['requests', filters], ...)` calls `apiFetch('/requests?...')` with status/urgency/product_id filters
- TanStack Table with `getPaginationRowModel` (10 rows/page) + `getSortedRowModel`
- Sortable columns: Time, Volume, Target Price (ArrowUpDown icon in header buttons)
- Row click sets `?id=` URL param (selected row `bg-background-tertiary`)
- `aria-sort` on sortable column headers; `role="row"` + `aria-selected` on rows; keyboard (Enter/Space) row activation
- Status chip via `StatusChip`, urgency chip via `UrgencyChip` (shared from 04-03)
- Empty state: `Inbox` icon + "No requests found" / "Try adjusting your filters or check back later."

**RequestsFilterBar** (`"use client"`):
- Period, Urgency, Status selects (plain `<select>` with token classes — avoids useCallback memoization lint errors)
- Filter state persisted in URL search params via `useSearchParams` + `router.replace`
- Active filter chips (removable via X button with `aria-label="Remove {filter} filter"`)
- "Clear filters" text button (accent, only visible when active filters exist)

**ExportCsvButton** (`"use client"`):
- Reads current URL search params, builds `/requests/export?...` with active filters
- Uses `fetch()` with JWT Bearer token, creates blob download link (`URL.createObjectURL`)
- Loading state (spinner), error banner on failure (copywriting: "Export failed…")

**requests/page.tsx** (`"use client"` — required for Lucide icons as KpiCard props):
- Header: "Purchase Requests" title + subtitle, Search input, `<ExportCsvButton>` in Suspense, Settings icon button (44px), "● Live Data" pulsing dot (accent, "Live Data" label)
- 6 KPI cards: Total Requests, Total Volume, Avg Target Price, Hot Requests, Sources, Updated
- `<RequestsFilterBar>` in Suspense
- `<RequestsTable>` in Suspense with loading fallback
- `<RequestDetailPanel>` in Suspense (mounts when `?id=` is set)

### Task 3: Detail Sheet + AI Block + Actions

**RequestDetailPanel** (`"use client"`):
- `Sheet side="right"` from shadcn, 400px fixed width, opened/closed via `?id=` URL param
- `role="dialog"` + `aria-labelledby="request-detail-heading"` on SheetContent
- `useQuery(['request', selectedId], ...)` from `/requests/{id}`
- Header: `StatusChip`, request number (mono), product title (20px semibold), grade/urgency chips, close X button (44px)
- Sections: Request Details (dl grid), Source Information (Asia/Tashkent `<time>`), AI Analysis, Files, Actions

**AiAnalysisBlock** (D-01/D-02):
- Match Score: `<div role="progressbar">` + accent fill bar at `0%`/"—" in Phase 4 (D-01 placeholder)
- Price Analysis: REAL from `price_analysis` (D-02) — `text-accent` when delta≥0, `text-urgency-medium` when delta<0; "No price data available" when null
- Demand Level: "Pending (Phase 5)" (D-01 placeholder)
- Recommendation: "AI analysis available after Phase 5" italic `text-foreground-subtle` (D-01 placeholder)

**RequestActions** (D-10/D-11/D-12):
- **Contact Buyer**: `POST /requests/{id}/contact` then `window.open(data.tg_link)`. Disabled + tooltip "No Telegram ID on file" when `contact_available=false` (Pitfall 6 / T-04-17 / D-11)
- **Add Note**: inline 4-row textarea, `POST /requests/{id}/note` on Save; cancel resets
- **Status dropdown**: `<select>` → `PATCH /requests/{id}`; `AlertDialog` confirm for "cancelled" with copywriting-contract text ("Cancel this request? This cannot be undone…")
- **Assign Owner**: `<select>` populated from `useQuery(['admin-users'])` → `GET /admin/users` → `POST /requests/{id}/assign`
- **Mark as Processed**: `PATCH status=closed`; disabled when already closed
- All mutations: `useMutation` → `invalidateQueries(['request', id])` + `['requests']`
- Error banner: "Status change failed. Refresh the page and try again." / "Note could not be saved…" (UI-SPEC copywriting)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] requests/page.tsx needed "use client" directive**
- **Found during:** Task 3 build verification
- **Issue:** Next.js App Router cannot pass function/component props (Lucide icons) from a Server Component to a Client Component (KpiCard). The build errored with "Functions cannot be passed directly to Client Components."
- **Fix:** Added `"use client"` directive at the top of `requests/page.tsx`. The Suspense boundaries around `RequestsFilterBar`, `RequestsTable`, and `RequestDetailPanel` still work correctly within a client page. Pre-rendering was unaffected (page renders as static content).
- **Files modified:** `dashboard/app/(dashboard)/requests/page.tsx`
- **Commit:** 8d80a7c

**2. [Rule 1 - Bug] useCallback in RequestsFilterBar caused React Compiler memoization errors**
- **Found during:** Task 2 lint
- **Issue:** `useCallback` with `[router, searchParams]` dependencies triggered `react-hooks/preserve-manual-memoization` errors — the React Compiler could not preserve the memoization given the `ReadonlyURLSearchParams` object type.
- **Fix:** Converted `setParam`, `removeFilter`, `clearFilters` to plain function declarations (no `useCallback`) as the filter bar does not have memoization-sensitive children.
- **Files modified:** `dashboard/components/requests/RequestsFilterBar.tsx`
- **Commit:** dc2c1a1

**3. [Rule 1 - Bug] Unused imports in ExportCsvButton and RequestActions**
- **Found during:** Task 2/3 lint
- **Issue:** `apiFetch` imported but unused in ExportCsvButton; `AlertDialogTrigger` imported but unused in RequestActions.
- **Fix:** Removed unused imports.
- **Files modified:** ExportCsvButton.tsx, RequestActions.tsx
- **Commit:** dc2c1a1, 8d80a7c

## Verification Results

**Task 1:**
- `pytest tests/test_requests_export.py -x -q` → 6 passed, 0 failed
- `dashboard_requests.py` contains `text/csv`, `Content-Disposition`, `csv.writer` usage
- Export route guarded by `get_current_staff_user`

**Task 2:**
- `RequestsTable.tsx` uses `['requests'` query key, renders `StatusChip` and `UrgencyChip`
- `requests/page.tsx` contains "Export CSV" control and "Live Data" indicator
- No hardcoded hex: `grep -rE "#[0-9a-fA-F]{6}" dashboard/components/requests/` → nothing
- `npm run typecheck` → exit 0
- `npm run lint` → exit 0 (2 warnings: TanStack Table incompatible-library — expected, same as 04-03)

**Task 3:**
- `RequestDetailPanel.tsx` uses `side="right"` and `role="dialog"` + `aria-labelledby`
- `AiAnalysisBlock.tsx` contains "after Phase 5" + price_analysis delta classes (accent/urgency-medium)
- `RequestActions.tsx` contains "Contact Buyer", status select, Assign Owner from `/admin/users`, "Mark as Processed", `useMutation`, `invalidateQueries(['request'`
- `npm run typecheck` → exit 0
- `npm run lint` → exit 0 (2 warnings)
- `npm run build` → 7 routes (/, /_not-found, /login, /offers, /requests, /signals) — all static

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| KPI card values all "—" (Total Requests, Volume, Avg Price, Hot Requests, Sources, Updated) | `app/(dashboard)/requests/page.tsx` | No aggregate KPI endpoint for /requests in Phase 4. Cards render in final shape (D-01 contract); data wired when KPI endpoint is added in a later plan. |
| Region column returns "—" | `RequestsTable.tsx` | `RequestListOut` schema (04-04) does not include a `region` or `source` field. Column structure matches UI-SPEC; server-side field extension deferred. |
| Source column returns "—" | `RequestsTable.tsx` | Same as above. |

All stubs are by design and do not prevent the plan goal (flagship master-detail renders; actions round-trip; CSV export works).

## Threat Surface Scan

All threat mitigations from the plan's threat model are implemented:

| Threat | Status |
|--------|--------|
| T-04-15 XSS (request fields, notes) | Mitigated — no `dangerouslySetInnerHTML` anywhere; all data rendered as React text nodes |
| T-04-16 Elevation (viewer role) | Mitigated — UI disables write action buttons via `disabled` prop; server `require_role` is the real gate (04-04) |
| T-04-17 Contact Buyer NULL telegram_user_id | Mitigated — `contact_available=false` disables button + shows tooltip "No Telegram ID on file"; no `tg://user?id=None` ever opened |
| T-04-18 DoS (CSV export large result) | Mitigated — `StreamingResponse` + `.limit(50_000)` in backend; frontend streams as blob |
| T-04-SC npm installs | Accepted — no new packages; all components use shadcn + hooks from 04-02/04-03 |

No new trust boundaries or network endpoints beyond what is specified in the plan's threat model.

## Self-Check: PASSED

Created files verified on disk:
- FOUND: dashboard/components/requests/RequestsTable.tsx
- FOUND: dashboard/components/requests/RequestsFilterBar.tsx
- FOUND: dashboard/components/requests/ExportCsvButton.tsx
- FOUND: dashboard/components/requests/RequestDetailPanel.tsx
- FOUND: dashboard/components/requests/AiAnalysisBlock.tsx
- FOUND: dashboard/components/requests/RequestActions.tsx
- FOUND: dashboard/app/(dashboard)/requests/page.tsx
- FOUND: backend/tests/test_requests_export.py
- FOUND: backend/app/api/dashboard_requests.py (modified)

Task commits verified in git log:
- FOUND: 5a522e9 (Task 1: export endpoint + test)
- FOUND: dc2c1a1 (Task 2: table + filter bar + page)
- FOUND: 8d80a7c (Task 3: detail panel + AI block + actions)
