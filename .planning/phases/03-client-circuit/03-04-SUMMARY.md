---
phase: 03-client-circuit
plan: "04"
subsystem: ui
tags: [react, vite, telegram, webapp, wizard, i18n, zustand, react-hook-form, zod, react-router-dom, lucide-react]

# Dependency graph
requires:
  - phase: 03-01
    provides: initData auth dep, upload validation service, /webapp Pydantic schemas, S3 client
  - phase: 03-02
    provides: /webapp/requests POST, /webapp/requests/{id}/files POST, /webapp/me endpoints

provides:
  - Telegram Web App shell with HashRouter + i18n (ru/uz) + Telegram SDK wrapper
  - initData-authed typed API client with X-Telegram-Init-Data header on every call
  - Zustand client-only wizard store (step, all wizard fields, staged files)
  - 5 shared components: StepIndicator, FieldGroup, SelectField, FileUploader, StatusChip
  - 5 screens: Home (C-01), Step1 (C-02), Step2 (C-03), Step3 (C-04), Confirm (C-05)
  - RU/UZ i18n bundles with full Copywriting Contract key parity (73+ keys)
  - Production build ≤91 KB gzip (within ≤300 KB budget)
  - Sequential file upload flow (for-await, not Promise.all — 3G budget)

affects: [03-05, 03-06, 03-03]

# Tech tracking
tech-stack:
  added:
    - react-router-dom (route-level code-splitting via React.lazy + Suspense)
    - lucide-react (line icon set per UI-SPEC)
  patterns:
    - HashRouter for Telegram Web App URL safety (fragment routing avoids Telegram URL conflicts)
    - Telegram SDK via thin telegram.ts wrapper (initTelegram, getInitData, mainButton, backButton, haptics)
    - i18n language derived from Telegram language_code (uz prefix -> uz, else ru) — D-04
    - react-hook-form + zodResolver for per-step blocking validation (D-02: product_id + volume + grade_text-or-polymer_type)
    - Client-side file validation before staging (not on submit) — >5 files / >10 MB / non-allowlisted MIME
    - Sequential file upload (for-await loop per file, not Promise.all) for 3G budget
    - tg-theme vars (var(--tg-theme-*)) for all colors; only hardcoded hex is #ef4444

key-files:
  created:
    - webapp/src/telegram.ts
    - webapp/src/types.ts
    - webapp/src/api/client.ts
    - webapp/src/store/wizardStore.ts
    - webapp/src/i18n/index.ts
    - webapp/src/i18n/ru.json
    - webapp/src/i18n/uz.json
    - webapp/src/components/StepIndicator.tsx
    - webapp/src/components/FieldGroup.tsx
    - webapp/src/components/SelectField.tsx
    - webapp/src/components/FileUploader.tsx
    - webapp/src/components/StatusChip.tsx
    - webapp/src/pages/Home.tsx
    - webapp/src/pages/wizard/Step1.tsx
    - webapp/src/pages/wizard/Step2.tsx
    - webapp/src/pages/wizard/Step3.tsx
    - webapp/src/pages/wizard/Confirm.tsx
  modified:
    - webapp/src/main.tsx
    - webapp/src/App.tsx
    - webapp/index.html
    - webapp/package.json

key-decisions:
  - "HashRouter chosen over BrowserRouter for Telegram Web App URL safety — fragment routing avoids URL conflicts in Telegram's embedded browser"
  - "Task 0 (npm legitimacy gate): react-router-dom and lucide-react both verified on npmjs.com by human; approved before install"
  - "Task 3 (wizard flow verification): human-verified frontend at http://localhost:5173; step 6 submit→REQ-number→confirmation deferred to 03-06 E2E acceptance plan by explicit user agreement (frontend-only scope, backend not running during verify)"
  - "Sequential file upload (for-await, not Promise.all) to respect 3G connection budget per D-01"
  - "i18n default language reads Telegram language_code: starts with 'uz' -> uz, else ru (D-04)"
  - "Product list sourced from static localized constant (PP/HDPE/LDPE/LLDPE/PVC/PET/PS/ABS) — no GET /products endpoint in this phase"
  - "React.lazy + Suspense for route-level code-splitting; bundle landed at ~91 KB gzip vs ≤300 KB budget"

patterns-established:
  - "Telegram SDK wrapper pattern: all mainButton/backButton/haptic calls go through telegram.ts; screens never call @telegram-apps/sdk directly"
  - "Wizard state pattern: client-only zustand store survives minimize (in-memory); no server persistence in the store (D-01)"
  - "API client pattern: apiFetch injects X-Telegram-Init-Data on every call including multipart uploads (do NOT set Content-Type for FormData — browser sets boundary)"
  - "tg-theme color pattern: all backgrounds/text use var(--tg-theme-*); accent = tg-theme-button-color; only hardcoded hex #ef4444 for errors"

requirements-completed: [REQ-request-wizard, REQ-webapp-i18n, REQ-webapp-auth, REQ-nfr-performance]

# Metrics
duration: ~90min
completed: "2026-06-16"
---

# Phase 03 Plan 04: Web App Frontend Core Summary

**React/Vite Telegram Web App with 4-step request wizard, RU/UZ i18n, initData-authed API client, and zustand wizard store; production bundle ~91 KB gzip (within ≤300 KB budget)**

## Performance

- **Duration:** ~90 min (across two implementation sessions + human verification)
- **Started:** 2026-06-16
- **Completed:** 2026-06-16
- **Tasks:** 4 (Task 0: human gate — approved; Task 1: auto; Task 2: auto; Task 3: human gate — approved)
- **Files modified:** 21

## Accomplishments

- Delivered the full client-facing request submission flow: Home (C-01) → 4-step wizard (C-02..C-04) → Confirmation (C-05) with per-step zod blocking validation, Telegram MainButton/BackButton control, and sequential file upload
- Shipped RU/UZ i18n with full Copywriting Contract key parity (73+ keys), TG language_code default (D-04), and tg-theme var styling throughout
- Production build passes at ~91 KB gzip — well within the ≤300 KB REQ-nfr-performance budget; route-level code-splitting via React.lazy keeps first paint on budget

## Task Commits

1. **Task 0: Package legitimacy gate (react-router-dom, lucide-react)** — No commit (human-only gate; packages approved by user after npmjs.com verification)
2. **Task 1: App shell — router, i18n, Telegram SDK wrapper, types, API client, wizard store** — `c6978d5` (feat)
3. **Task 2: Components + screens C-01..C-05** — `67a604f` (feat)
4. **Task 3: Human-verify wizard flow + Telegram integration** — No commit (human-only gate; approved with noted deferral)

**Plan metadata:** (this commit)

## Files Created/Modified

**Created:**
- `webapp/src/telegram.ts` — thin @telegram-apps/sdk wrapper: initTelegram, getInitData, mainButton, backButton, haptic helpers
- `webapp/src/types.ts` — TS interfaces mirroring schemas/webapp.py (RequestCreate, RequestOut, RequestDetail, StatusHistory, RequestFileMeta, ClientProfile)
- `webapp/src/api/client.ts` — apiFetch with X-Telegram-Init-Data header, ApiError, typed api surface (createRequest, getRequests, getRequest, uploadFile, getMe, patchMe)
- `webapp/src/store/wizardStore.ts` — zustand client-only wizard store (step, all wizard fields, files:File[], actions)
- `webapp/src/i18n/index.ts` — i18next + react-i18next config, TG language_code default (uz/ru), localStorage persist
- `webapp/src/i18n/ru.json` — full RU translation bundle (73+ keys: home.*, wizard.*, confirm.*, myRequests.*, error.*, status.*)
- `webapp/src/i18n/uz.json` — full UZ translation bundle with exact key parity to ru.json
- `webapp/src/components/StepIndicator.tsx` — 4-dot step indicator (active/past/future states)
- `webapp/src/components/FieldGroup.tsx` — label + input + inline zod error with aria-describedby
- `webapp/src/components/SelectField.tsx` — native `<select>` styled with tg-theme vars
- `webapp/src/components/FileUploader.tsx` — file input with client-side validation (>5 / >10 MB / non-allowlisted MIME), staged list with × remove, haptic feedback
- `webapp/src/components/StatusChip.tsx` — status pill with D-10 color map and localized text label (color + text, never color alone)
- `webapp/src/pages/Home.tsx` — C-01 Home screen with accent CTA, value props, no blocking API call on mount
- `webapp/src/pages/wizard/Step1.tsx` — C-02 product/grade/volume form (zod D-02: product_id + volume + grade_text-or-polymer_type required)
- `webapp/src/pages/wizard/Step2.tsx` — C-03 delivery terms (all optional, state preserved on back-nav)
- `webapp/src/pages/wizard/Step3.tsx` — C-04 comment + FileUploader, MainButton label changes to "Отправить"
- `webapp/src/pages/wizard/Confirm.tsx` — C-05 confirmation with success icon, REQ number display, StatusChip "Новая заявка", sequential file upload logic

**Modified:**
- `webapp/src/main.tsx` — HashRouter + I18nextProvider + initTelegram() before render
- `webapp/src/App.tsx` — route table with React.lazy + Suspense for all screens, tg-theme styles preserved
- `webapp/index.html` — `<html lang="ru">`, Telegram web-app meta/script
- `webapp/package.json` — added react-router-dom and lucide-react

## Decisions Made

- **HashRouter over BrowserRouter:** Telegram's embedded browser has URL constraints; fragment-based routing avoids conflicts and does not require server-side routing config.
- **Product list as static constant:** No GET /products endpoint exists in this phase. Seeded polymer set (PP/HDPE/LDPE/LLDPE/PVC/PET/PS/ABS) sourced from reference.py is hardcoded as a localized static constant in Step1. 03-05 or a future plan can replace with a live endpoint.
- **Sequential file upload (for-await):** Files are uploaded one-by-one after request creation, not in parallel (Promise.all), to respect 3G connection budget (D-01).
- **Submit→REQ-number path deferred to 03-06:** Task 3 human-verify covered frontend-only scope (steps 1–5 of 7). Step 6 (submit → confirmation with real REQ number) requires the backend to be running and was explicitly deferred to the 03-06 E2E acceptance plan by user agreement. This is a noted deferral, NOT a defect.

## Deviations from Plan

None — plan executed exactly as specified. The Task 3 deferral (submit→backend path) is an explicit user agreement recorded in the plan's verification scope, not a deviation.

## Known Stubs

- **Confirm.tsx — submit path:** The full submit→`api.createRequest`→sequential upload→real REQ number flow is implemented in code but was not end-to-end verified in Task 3 (no backend running during frontend-only verify). Verified against the backend in 03-06 E2E acceptance plan.
- **Routes for 03-05 screens:** `/requests`, `/requests/:id`, `/notifications`, `/settings` routes are registered in App.tsx pointing to placeholder lazy-imports. These screens are built in 03-05-PLAN.md.

## Issues Encountered

None beyond the noted deferral.

## User Setup Required

None — no external service configuration required for this plan's implementation. The running Telegram Web App requires the backend from 03-01/03-02 and a valid Telegram initData fixture for full end-to-end testing.

## Next Phase Readiness

- **03-03-PLAN.md** (aiogram bot): Can proceed in parallel — no file overlap with this plan.
- **03-05-PLAN.md** (Мои заявки + my-requests screens): Can proceed — the App.tsx route table, api/client.ts, store, i18n, and shared components are all in place for 03-05 to build on.
- **03-06-PLAN.md** (E2E acceptance gate): Will close out the submit→REQ-number→confirmation path verification (Task 3 noted deferral) and verify the full 5 Phase-3 success criteria on a live stack.

---
*Phase: 03-client-circuit*
*Completed: 2026-06-16*
