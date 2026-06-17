---
phase: 04-dashboard-source-constructor
plan: "02"
subsystem: dashboard-frontend
tags: [shadcn, auth-shell, tanstack-query, sse, jwt, dashboard]
dependency_graph:
  requires: [04-01]
  provides: [dashboard-shell, useSSE, useAuth, apiFetch, queryClient, formatTashkent]
  affects: [04-03, 04-04, 04-05, 04-06, 04-07, 04-08]
tech_stack:
  added:
    - shadcn/ui v4.11.0 (CLI installer, not runtime dep)
    - "@radix-ui/react-* primitives (auto-installed by shadcn)"
    - tw-animate-css v1.4.0
  patterns:
    - Route group (dashboard) auth guard via useAuth + useRouter
    - TanStack QueryClient singleton with staleTime=30s
    - EventSource SSE hook with exponential backoff + 30s polling fallback
    - JWT memory store (no localStorage, T-04-06)
    - CSS-var dark token reconciliation (shadcn vars → existing Tailwind tokens)
key_files:
  created:
    - dashboard/components.json
    - dashboard/app/globals.css
    - dashboard/components/ui/ (19 shadcn components)
    - dashboard/lib/api.ts
    - dashboard/lib/queryClient.ts
    - dashboard/lib/tz.ts
    - dashboard/hooks/useSSE.ts
    - dashboard/hooks/useAuth.ts
    - dashboard/components/layout/Sidebar.tsx
    - dashboard/components/layout/AppShell.tsx
    - dashboard/app/(dashboard)/layout.tsx
    - dashboard/app/(dashboard)/page.tsx
    - dashboard/lib/utils.ts
  modified:
    - dashboard/app/login/page.tsx (handleSubmit wired)
    - dashboard/app/layout.tsx (shadcn Geist font added)
decisions:
  - "shadcn@4.11.0 generates Tailwind v4 CSS syntax (--spacing(), OKLCH, tw-animate-css, shadcn/tailwind.css imports); project uses Tailwind v3 — reconciled by rewriting card.tsx (--spacing() → direct spacing classes), calendar.tsx (--spacing(7) → 1.75rem), globals.css (removed tw-animate-css + shadcn/tailwind.css imports, reverted to hsl() CSS vars)"
  - "CSS vars use hsl() format (not OKLCH) for Tailwind v3 compatibility: --background: 222 47% 11% maps #0f172a, --primary: 160 84% 39% maps #10b981 accent"
  - "useSSE ref update moved to useEffect (react-hooks/refs lint rule requires ref mutations outside render)"
  - "calendar.tsx ClassNames key: table → month_grid (react-day-picker v9 compat with shadcn v4 generated code)"
metrics:
  duration: "8 minutes"
  completed: "2026-06-17"
  tasks: 2
  files_created: 27
  files_modified: 4
---

# Phase 04 Plan 02: Dashboard Foundation Summary

shadcn/ui initialized with CSS vars reconciled to locked Tailwind v3 dark tokens; TanStack QueryClient singleton, typed apiFetch with 401 redirect, Intl-based Asia/Tashkent formatter, JWT auth hook, EventSource SSE hook with backoff + 30s polling fallback, 240px auth-guarded sidebar + AppShell, and wired login submit.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | shadcn init + token reconciliation + lib utilities + hooks | 6d35f39 | components.json, globals.css, lib/*, hooks/*, components/ui/* |
| 2 | Auth-guarded shell + Sidebar + AppShell + login submit | f831917 | layout/Sidebar.tsx, layout/AppShell.tsx, (dashboard)/layout.tsx, login/page.tsx |

## What Was Built

### Task 1: shadcn init + Foundation Utilities

**shadcn/ui initialized:**
- `components.json` references `app/globals.css` and `tailwind.config.ts`
- 19 UI components added: button, input, select, dialog, alert-dialog, table, badge, card, tabs, separator, tooltip, popover, dropdown-menu, sheet, skeleton, command, calendar, textarea, input-group
- `tailwind.config.ts` unchanged — all token values preserved

**CSS var reconciliation (globals.css):**
- `.dark` block maps shadcn vars to locked Polymer Intelligence token hex values using hsl() format
- `--background: 222 47% 11%` (#0f172a), `--card: 215 28% 17%` (#1e293b), `--primary: 160 84% 39%` (#10b981), `--border: 215 19% 27%` (#334155), `--ring: 160 84% 39%` (#10b981)

**lib/queryClient.ts:** `QueryClient` singleton, `staleTime: 30_000` (aligns with SSE polling fallback).

**lib/api.ts:** `apiFetch<T>(path, init?)` — prefixes `/api/v1`, attaches `Authorization: Bearer ${token}`, parses JSON, redirects to `/login` on 401. `setToken`/`getToken` for memory-only JWT storage (T-04-06: no DOM/log echo).

**lib/tz.ts:** `formatTashkent`, `formatTashkentDate`, `relativeTime` via `Intl.DateTimeFormat` with `timeZone: 'Asia/Tashkent'` (DEC-tz-handling).

**hooks/useAuth.ts:** JWT memory store, `parseJwtPayload`, `isTokenExpired`, `login(token)`, `logout()`, `isAuthenticated`.

**hooks/useSSE.ts:** `useSSE(url, onMessage)` — `new EventSource(url, { withCredentials: true })`, exponential backoff 1s → cap 30s (reset on success), 30s polling fallback that calls `onMessage('poll')`. DEC-realtime-sse-not-websocket.

### Task 2: Auth-guarded Shell

**components/layout/Sidebar.tsx:**
- 240px fixed `bg-background-secondary`, logo + "Polymer Intelligence" wordmark (`text-accent`)
- Four nav groups: MAIN (Dashboard, Live Feed), REQUESTS (Purchase Requests, Offers), SOURCES (Sources, Alerts), SETTINGS (Prices, Admin Users)
- Active item: `border-l-2 border-accent bg-background-tertiary text-foreground`
- 12px uppercase group labels `text-foreground-muted tracking-wider`
- Role-gate: Admin Users hidden for non-admin roles
- User footer: initials circle + email + role badge
- `usePathname` for active state, no hardcoded hex

**components/layout/AppShell.tsx:** `flex h-screen overflow-hidden` — fixed Sidebar + `flex-1 overflow-y-auto` main.

**app/(dashboard)/layout.tsx:** `"use client"`, `useAuth().isAuthenticated` checked in `useEffect` → `router.push('/login')` on absent/expired JWT (T-04-05). Wraps children in `QueryClientProvider + AppShell`.

**app/(dashboard)/page.tsx:** Dashboard home placeholder — page header + `data-slot="dashboard-grid"` container for Plan 04-03 KPI cards.

**app/login/page.tsx:** `handleSubmit` wired to `POST /api/v1/auth/login` via `apiFetch`, stores token via `useAuth().login()`, `router.push('/')` on success, error banner on failure, loading state.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] shadcn v4 generates Tailwind v4 CSS syntax incompatible with Tailwind v3**
- **Found during:** Task 1/2 build
- **Issue:** shadcn@4.11.0 (--defaults) chose "base-nova" style which generates: (a) `@import "tw-animate-css"` and `@import "shadcn/tailwind.css"` imports in globals.css that Next.js v16/Turbopack cannot resolve via CSS `@import`, (b) `--spacing()` CSS function in card.tsx and calendar.tsx (Tailwind v4 syntax), (c) OKLCH color format
- **Fix:** (a) Removed incompatible CSS `@import`s from globals.css; replaced OKLCH with hsl() vars for shadcn component internals; (b) Rewrote card.tsx replacing `[--card-spacing:--spacing(4)]` with direct `gap-4 py-4` spacing classes; fixed calendar.tsx `[--cell-size:--spacing(7)]` → `[--cell-size:1.75rem]`
- **Files modified:** `dashboard/app/globals.css`, `dashboard/components/ui/card.tsx`, `dashboard/components/ui/calendar.tsx`
- **Commit:** f831917

**2. [Rule 1 - Bug] calendar.tsx ClassNames key 'table' not valid in react-day-picker**
- **Found during:** Task 1 typecheck
- **Issue:** shadcn generated `table: "w-full border-collapse"` but the installed react-day-picker uses `month_grid` as the key
- **Fix:** Changed `table` → `month_grid`
- **Files modified:** `dashboard/components/ui/calendar.tsx`
- **Commit:** 6d35f39

**3. [Rule 1 - Bug] useSSE.ts updating ref during render violates react-hooks/refs**
- **Found during:** Task 1 lint
- **Issue:** `onMessageRef.current = onMessage` at render time triggers ESLint `react-hooks/refs` error
- **Fix:** Moved ref update into `useEffect(() => { onMessageRef.current = onMessage; }, [onMessage])`
- **Files modified:** `dashboard/hooks/useSSE.ts`
- **Commit:** 6d35f39

**4. [Rule 1 - Bug] Sidebar imported unused icons causing lint errors**
- **Found during:** Task 2 lint
- **Issue:** `AlertCircle` and `Settings` imported but not used
- **Fix:** Removed unused imports
- **Files modified:** `dashboard/components/layout/Sidebar.tsx`
- **Commit:** f831917

## Verification Results

All acceptance criteria passed:
- `dashboard/components.json` references `app/globals.css` and `tailwind.config.ts`
- `dashboard/hooks/useSSE.ts` exports `useSSE`, contains `new EventSource`, contains `30_000`
- `dashboard/lib/api.ts` contains `Authorization` and `/login` redirect
- `dashboard/lib/tz.ts` contains `Asia/Tashkent`
- `dashboard/tailwind.config.ts` — no changes (git diff --stat shows empty)
- `dashboard/components/layout/Sidebar.tsx` contains `bg-background-secondary`, all four nav groups, no hardcoded hex
- `dashboard/app/(dashboard)/layout.tsx` contains `QueryClientProvider` and `/login` auth redirect
- `dashboard/app/login/page.tsx` posts to `auth/login` (no longer a TODO stub)
- `npm run typecheck` — exit 0
- `npm run lint` — exit 0
- `npm run build` — completes successfully (route group compiles)

## Known Stubs

The `dashboard/app/(dashboard)/page.tsx` is an intentional placeholder — the KPI grid is filled by Plan 04-03. The placeholder renders a holding message; the plan goal (auth guard working, route compiles) is fully achieved.

## Threat Surface Scan

No new security surface introduced beyond what the threat model covers:
- T-04-05 (auth guard): mitigated — `isAuthenticated` check in `useEffect` → redirect
- T-04-06 (token handling): mitigated — `setToken`/`getToken` memory-only; 401 redirects without echoing token
- T-04-07 (XSS): mitigated — React escape by default, no `dangerouslySetInnerHTML`, no hardcoded hex
- T-04-SC (shadcn CLI): accepted — `@4.11.0` from official shadcn-ui org

## Self-Check

Checking critical files exist:

- FOUND: dashboard/components.json
- FOUND: dashboard/hooks/useSSE.ts
- FOUND: dashboard/hooks/useAuth.ts
- FOUND: dashboard/lib/api.ts
- FOUND: dashboard/lib/queryClient.ts
- FOUND: dashboard/lib/tz.ts
- FOUND: dashboard/app/(dashboard)/layout.tsx
- FOUND: dashboard/app/(dashboard)/page.tsx
- FOUND: dashboard/components/layout/Sidebar.tsx
- FOUND: dashboard/components/layout/AppShell.tsx

Checking commits exist:
- FOUND: 6d35f39
- FOUND: f831917

## Self-Check: PASSED
