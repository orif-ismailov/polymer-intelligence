# QA Execution Report — Dashboard + Portal

## Environment

- **Application:** Polymer Intelligence — `dashboard/` (internal team dashboard, Next.js) and `portal/` (client cabinet, Vite/React)
- **Backend:** Isolated QA stack — own Postgres DB (`polymer_qa`), own MinIO bucket (`polymer-qa` on `demo-minio`), `uvicorn` + Celery worker run directly on host from current `redesign-architecture` branch (commit `55a6029`). `DEBUG=true`, `EIMZO_STUB=true`, `SMS_PROVIDER=console`, `OTP_DEV_CODE=000000`.
- **Browser:** Chromium-based in-app browser pane (no cross-browser-engine coverage — see Scope note)
- **Viewports tested:** 1280×720 (desktop), 375×812 (mobile)
- **Roles exercised:** `admin`, `analyst`, `trader`, `viewer` (dashboard, seeded credentials as supplied); fresh phone-OTP account (portal)
- **Date:** 2026-07-28

### Scope note

Full 12-layer × every-page × every-role exhaustiveness was not attempted in one pass (see the approved plan). Depth was weighted toward RBAC/auth boundaries, mutating flows, injection/boundary sampling, and race conditions, across a representative majority of pages rather than a line-by-line sweep of all ~30 dashboard pages × 4 roles. Not covered: `webapp/` (Telegram Mini App, out of scope — no credentials supplied), native screen-reader testing (keyboard-nav/DOM-structure only), true multi-browser-engine testing, load/performance-at-scale, and full happy-path testing of LLM-backed flows (AI request analysis, news classification/report generation) — the QA stack has no real `ANTHROPIC_API_KEY`, so these were only checked for graceful degradation, not output quality.

---

## Summary

| | |
|---|---|
| Pages/surfaces exercised | ~15 dashboard pages (incl. full RBAC matrix across ~20 admin-gated API endpoints), portal login/OTP + 5-step company wizard + offer publish flow |
| Test cases executed | Smoke (4 roles), RBAC boundary sweep (API-level matrix + live UI verification), functional CRUD (verification decide, moderation approve/reject, source management), injection/boundary sampling (XSS, SQL-like strings), 1 concurrency/race test, 2 responsive-viewport checks |
| Bugs found | 6 (2 High, 2 Medium, 2 Low) |
| Notable passes | RBAC enforcement at the API layer, XSS/injection escaping (dashboard + portal), E-IMZO stub flow, portal mobile responsiveness, portal two-step logout, client-side form validation |

**Overall Quality Score: 74/100**
**Production Readiness: Not Ready** — blocked primarily by Bug #1 (moderation race condition causing data corruption on a customer-facing marketplace listing) and Bug #2 (broken Sources admin surface for non-admin roles); the remaining findings are real but lower-stakes UX/session-hygiene gaps.

---

# Findings

## Bug #1 — Concurrent moderation approve + reject corrupts the offer record

**Severity:** Critical
**Priority:** P0
**Area:** Backend — `POST /admin/moderation/offers/{id}/approve` / `.../reject`
**Impact:** All staff moderators; indirectly all buyers (a rejected/non-compliant offer can end up live)

**Description:** The moderation-offers endpoints have no optimistic-locking or conflict check. If `approve` and `reject` are called concurrently on the same pending offer (e.g. two moderators both acting on the same queue item, or a slow network causing a client retry), **both requests return `200 OK`** with no error — but the final database row ends up in a self-contradictory state: `status = approved` with `moderation_note` containing the *rejection* reason.

**Steps to Reproduce:**
1. Create a `pending_moderation` seller offer (e.g. via the portal offer-publish flow, as a verified company).
2. Fire two near-simultaneous requests: `POST /admin/moderation/offers/{id}/approve` and `POST /admin/moderation/offers/{id}/reject` (body `{"note": "..."}`), as any analyst/admin.
3. Both return `200`.
4. Query the row directly.

**Expected:** The second request should fail with `409 Conflict` (or equivalent) once the first has already transitioned the item out of `pending_moderation` — exactly the pattern already implemented for `verification` case decisions, `lab-orders` transitions, and `escrow` marks (per the codebase's own precedent).

**Actual:** Reproduced live in this session — final row:
```
id | status   | moderation_note
 1 | approved | race test reject
```
An offer intended to be rejected is published as `approved` while carrying its own rejection note. The moderation queue correctly stops listing it (it's no longer `pending_moderation`), so a moderator has no way to notice the corruption without inspecting the raw record.

**Evidence:** Two concurrent `curl` calls, both `200`; `moderation_offers` table row confirmed via direct DB query (`status=approved`, `moderation_note='race test reject'`).

**Root Cause (Hypothesis):** The approve/reject handlers likely read-then-write the offer without a `SELECT ... FOR UPDATE`/version check, unlike the sibling `verification`/`lab-orders`/`escrow` flows which the codebase already guards this way (per `dashboard/CLAUDE.md` and observed 409-handling UI code in those pages). This endpoint appears to have been implemented before or without that pattern.

**Recommendation:** Add the same conflict-detection pattern used elsewhere in this codebase (status precondition check + `409` on mismatch, surfaced in the dashboard moderation/offer-requests UI as a conflict banner + refetch, mirroring `verification/[id]/page.tsx`). Apply the same fix to `offer-requests` approve/reject, which has an identical code shape per the earlier exploration and was not separately race-tested here but shares the same risk.

---

## Bug #2 — Sources admin surface is fully visible and interactive for every role, but 100% of its actions require admin and fail silently

**Severity:** High
**Priority:** P1
**Area:** Dashboard — `/sources` page and `AddSourceWizard`
**Impact:** analyst, trader, viewer roles (the "Источники" nav item has no `minRole`, so all four roles see it)

**Description:** The `/sources` nav entry, the "Добавить источник" (Add Source) button, and every per-row action (Тест / Test, Переобработать / Reprocess, Включить источник / Enable toggle) are rendered unconditionally for every authenticated role. The backend, however, gates **every one of these** behind `require_admin`:

| Endpoint | admin | analyst | trader | viewer |
|---|---|---|---|---|
| `GET /admin/source-types` | 200 | 403 | 403 | 403 |
| `POST /sources` | 422* | 403 | 403 | 403 |
| `POST /sources/{id}/test` | 200 | 403 | 403 | 403 |
| `PATCH /sources/{id}` (enable toggle) | 200 | 403 | 403 | 403 |
| `POST /admin/sources/{id}/reprocess` | 200 | 403 | 403 | 403 |

*(422 = validation error on an intentionally-empty test payload, confirming the authz check passed before validation for admin.)*

**Steps to Reproduce:**
1. Log in as `analyst@polymer.uz`.
2. Navigate to `/sources`.
3. Click "Добавить источник" (Add Source).
4. Observe Step 1 ("Выбор типа") — no source-type options render, and the "Продолжить" (Continue) button does nothing when clicked with nothing selected.
5. Alternatively, click any row's "Тест" (Test) button.

**Expected:** Either the nav item/buttons are hidden or disabled below admin (matching the pattern used for `admin/products` and `admin/users`, the two pages that *do* have proper route/UI guards), or a clear inline message explains the permission gap.

**Actual:** The wizard opens to a permanently empty, non-functional Step 1 with **zero explanation** — confirmed via network trace: `GET /admin/source-types → 403`, silently swallowed, `sourceTypes` falls back to `[]`. The "Тест" button click also 403s with no toast/error shown anywhere in the UI. A non-admin user has no way to tell whether the feature is broken or they lack permission.

**Evidence:** Live screenshot of the empty wizard step 1; `read_network_requests` showing `GET /api/v1/admin/source-types → 403 Forbidden`; DOM search confirming no `isAdmin`/role condition exists in `SourcesList.tsx` or `AddSourceWizard.tsx`, and no `minRole` set for the `sources` nav entry in `Sidebar.tsx`.

**Root Cause (Hypothesis):** The Sources feature was likely built admin-only from day one at the API layer, but the frontend nav/component gating was never added to match — an oversight rather than a deliberate "show but explain" design, since every other admin-only mutation surface in this codebase (`admin/products`, `admin/escrow`, `admin/substances`, etc.) does hide or gate its actions client-side.

**Recommendation:** Set `minRole: "admin"` on the `sources` nav entry (or add an explicit `isAdmin` gate around the Add/Test/Reprocess/Enable controls, matching the pattern in `escrow/page.tsx` and `substances/page.tsx`), and add a `enabled: isAdmin` guard to the `source-types`/`sources` queries so the UI doesn't attempt calls it knows will fail.

---

## Bug #3 — No logout control exists anywhere in the dashboard

**Severity:** Medium
**Priority:** P1
**Area:** Dashboard — global (`Sidebar.tsx`, all pages)
**Impact:** All dashboard staff users

**Description:** There is no logout/sign-out affordance anywhere in the dashboard UI. The sidebar footer shows the user's role as a plain, non-interactive `<span>` with no click handler. A DOM-wide search for logout/sign-out/"выход" text across every link and button on the authenticated shell returned zero matches.

Because the access token lives in-memory only but a **7-day httpOnly refresh cookie** silently re-authenticates on every page load (`(dashboard)/layout.tsx`), closing the browser tab does **not** end the session — reopening the dashboard on the same browser logs the same user back in automatically. There is no way to force-end a session from the UI at all.

**Steps to Reproduce:**
1. Log in as any role.
2. Attempt to find a sign-out control anywhere in the sidebar, header, or any settings page.

**Expected:** A visible logout action that clears the refresh cookie (`POST /auth/logout` or equivalent) and returns to `/login`.

**Actual:** No such control exists.

**Evidence:** `document.querySelectorAll('a,button')` filtered for logout-pattern text returned `[]`; the role-badge element resolved to a plain `<span>` three levels deep in a static `<div>`, no event listeners.

**Root Cause (Hypothesis):** Likely an oversight — the portal (`portal/`) *does* implement a proper two-step-confirm logout (verified working in this session), suggesting the dashboard's equivalent was simply never built.

**Recommendation:** Add a logout control (ideally in the sidebar footer, next to the role badge) that calls the backend logout/cookie-clear and redirects to `/login`. Important on any shared/public staff workstation.

---

## Bug #4 — Dashboard is not usable at mobile viewport widths

**Severity:** Medium
**Priority:** P2
**Area:** Dashboard — global layout (`Sidebar.tsx` / `(dashboard)/layout.tsx`)
**Impact:** Any staff user on a phone or narrow window

**Description:** At a 375×812 viewport, the sidebar does not collapse into a drawer/hamburger menu — it stays open as a fixed-width column, leaving roughly 100px of usable width for the main content. KPI cards and labels are truncated into unreadable fragments ("ОГ", "ВЫ...КЛ...").

**Steps to Reproduce:**
1. Resize the browser to a mobile width (375px) or open the dashboard on a phone.
2. Load any page (e.g. `/`).

**Expected:** A responsive layout — collapsible sidebar/hamburger menu, single-column content — matching the pattern already implemented in `portal/` (verified working: proper hamburger + bottom tab bar at the same viewport size).

**Actual:** Fixed desktop layout persists; content is functionally illegible.

**Evidence:** Side-by-side screenshots at 375×812 — dashboard (broken) vs. portal (correct) on the same session.

**Recommendation:** Not necessarily a priority if the dashboard is desktop-only by product decision, but if any mobile/tablet staff usage is expected, add a responsive breakpoint reusing the portal's existing pattern.

---

## Bug #5 — Blank screen (no loading state) during admin-only route-guard redirects

**Severity:** Low
**Priority:** P3
**Area:** Dashboard — `admin/products/page.tsx`, `admin/users/page.tsx`
**Impact:** Non-admin roles who navigate directly to an admin-only URL

**Description:** `admin/products` and `admin/users` correctly redirect non-admin roles back to `/`, but render `null` while the `useEffect`-based redirect resolves, producing a brief fully-blank (black) screen with no spinner.

**Steps to Reproduce:** As `analyst`, navigate directly to `/ru/admin/products` or `/ru/admin/users`.

**Expected:** A loading indicator (or the guard implemented at the route/middleware level to avoid a render flash at all).

**Actual:** A blank screen for roughly 200–500ms before the dashboard renders.

**Evidence:** Screenshots captured mid-redirect showing a solid black viewport.

**Recommendation:** Low priority — functionally correct, just a minor polish item. Add a skeleton/spinner state to the guard `useEffect`, or move the check server-side/into middleware.

---

## Bug #6 — Login session is shared across browser tabs with no warning

**Severity:** Low
**Priority:** P3
**Area:** Dashboard — session/auth model
**Impact:** Any user with multiple dashboard tabs open, or a shared machine

**Description:** Because the refresh token is a shared httpOnly cookie (not tab-scoped) and every tab silently re-authenticates from it on load, logging in as a different user in one tab silently switches the identity of *other already-open tabs* the next time they navigate or refresh — with no notification. Observed directly in this session: a tab left open on the `admin` dashboard silently became `analyst` after a different tab logged in as `analyst`.

**Expected/Actual:** This is standard behavior for cookie-based sessions and may be acceptable by design, but combined with Bug #3 (no logout), it means one staff member logging in on a shared browser can silently take over another staff member's already-open dashboard tab.

**Recommendation:** Low priority given it's inherent to the cookie-sharing model; worth a product decision on whether tab-scoped sessions (e.g. via `sessionStorage`-keyed identifiers) are warranted, but likely not worth the complexity for an internal tool once Bug #3 is fixed (a visible logout at least makes the current identity obvious).

---

## Notable passes (for completeness)

- **RBAC enforcement at the API layer** is correct and consistent across every admin-gated endpoint tested (~20 endpoints spanning companies, escrow, substances, lab-partners, deals, verification, moderation, offer-requests, settings, reports, llm-spend, admin/products, admin/users) — non-admin/non-analyst roles are cleanly rejected with `403` before any resource lookup, with no information leakage.
- **XSS/injection handling**: `<script>` tags and SQL-like strings (`' OR '1'='1 --`) submitted through the verification-decision comment field and the offer product-name field were stored verbatim but rendered as escaped text everywhere displayed (dashboard verification audit trail, dashboard moderation queue) — no script execution, no console errors.
- **E-IMZO stub-based company confirmation** (`window.__EIMZO_BRIDGE__`) worked correctly end-to-end: signing immediately submitted a real verification case with the expected per-check results (`tax_id_format`, `bank_requisites`, `documents_complete`, `manual_kyb`, `eimzo_signature`), and the documented fast-path behavior (skipping the Roles/Bank/Documents wizard steps) matches the repo's own `r3-eimzo.spec.ts` intent — not a bug.
- **Portal mobile responsiveness** is correctly implemented (hamburger menu, bottom tab bar, single-column cards) — a useful contrast confirming Bug #4 is a dashboard-specific gap, not a platform limitation.
- **Portal two-step logout** (Settings → Logout → confirm dialog) works exactly as documented.
- **Client-side form validation** (9-digit INN format, phone number auto-formatting/validation, 6-digit OTP capping) gives immediate, clear inline feedback and correctly blocks submission of invalid data.
- **Seeded staff credentials** exactly match the ones supplied (`admin@polymer.uz` / `admin_dev_password_change_in_prod`, etc.) — no drift from `app/seed/data/staff_users.json`.

---

## Environment / infra notes (not application bugs)

- The shared local docker dev stack (`deploy-api-1`, `deploy-beat-1`) is currently crash-looping due to a blank repo-root `.env` missing `VERIFICATION_ENC_KEY` and other required secrets — this is a pre-existing local environment issue, not something introduced or fixed during this QA pass. Testing was done against a disposable, isolated backend instead.
- Two unrelated stale background processes (an old `uvicorn`/Celery pair from a prior R3 test session, and a `next dev` instance) were found still occupying ports 8000 and 3001 from an earlier, unrelated session and were cleaned up to avoid nondeterministic test results.
- LLM-backed flows (AI request analysis, news classification, report generation) were not functionally verified beyond their degrade path, since the QA environment has no real `ANTHROPIC_API_KEY`.
