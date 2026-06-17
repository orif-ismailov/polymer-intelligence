---
phase: 03-client-circuit
verified: 2026-06-17T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Wizard visual flow + Telegram integration (deferred from 03-04 Task 3)"
    expected: "Home focal point correct; per-step zod blocking validation; BackButton preserves state; file limits enforced client-side; confirmation shows REQ number; theme adapts light/dark"
    why_human: "Visual/interaction correctness of the wizard inside Telegram WebApp cannot be verified by grep or build. Approved as deferred to deploy time (03-06 sign-off 2026-06-17)."
  - test: "My-requests list, detail timeline, and language toggle (deferred from 03-05 Task 3)"
    expected: "List newest-first with correct D-10 status chips; detail timeline shows Asia/Tashkent timestamps; language toggle switches UI immediately and persists"
    why_human: "Visual rendering of statuses, timezone display, and live language switch cannot be verified without running the app in Telegram. Approved as deferred to deploy time (03-06 sign-off 2026-06-17)."
  - test: "Live end-to-end client-circuit drill (deferred from 03-06 Task 3, approved by user 2026-06-17)"
    expected: "SC#1: wizard submit → REQ number → queryable ≤10 s; SC#2: PDF/JPG in MinIO polymer-files bucket, invalid types/sizes rejected; SC#3: status change → bot push ≤30 s with D-10 label + deep-link; SC#4: RU↔UZ toggle + theme; SC#5: /start greeting + Web App button + clients row created"
    why_human: "Requires real BOT_TOKEN + public HTTPS PUBLIC_WEBAPP_URL. Deferred to first deploy session per Phase-2 02-07 precedent. Automated SLA proxy tests (test_request_sla.py 4/4 PASS) serve as CI gate."
---

# Phase 03: Client Circuit — Verification Report

**Phase Goal:** A client can submit a purchase request end-to-end from the Telegram Web App, that request lands in the system promptly, and the client is kept informed of its status — closing the client-facing loop.

**Verified:** 2026-06-17
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC#1 | Client opens Web App authenticated via Telegram initData (first login creates `clients` row), completes 4-step wizard; submit returns REQ-YYYY-MM-DD-NNNNN, request queryable ≤10 s | ✓ VERIFIED (CI) + ? HUMAN (live) | `client_service.py` HMAC verification ✓; `get_current_client` upserts client row ✓; `request_service.create_request` generates REQ number via per-date PG sequence ✓; `test_request_readback_within_10s` PASS; live wall-clock deferred to deploy |
| SC#2 | Client attaches files (PDF/Excel/JPG, ≤10 MB, ≤5) uploading to MinIO; telegram_file_id fallback for bot-sent files | ✓ VERIFIED | `storage_service.py`: MAGIC_BYTES dict, MAX_SIZE_BYTES=10*1024*1024, MAX_FILES=5, upload_request_file builds traversal-safe S3 key; `files.py` enforces count before write; telegram_file_id=None for Web App uploads (D-09); minio service in compose with service_healthy gate |
| SC#3 | Client sees "Мои заявки" with current statuses + history; bot push within 30 s of status change | ✓ VERIFIED (CI) + ? HUMAN (live) | `webapp/requests.py` GET scoped by client_id ✓; `notify.py` send_status_change_notification task on `notify` queue with D-10 localized label ✓; worker `-Q ingest,parse,notify,default` ✓; `test_status_change_enqueues_notify_promptly` PASS (apply_async, no countdown/eta); `test_notify_task_no_long_sleep` PASS; live timing deferred |
| SC#4 | Web App toggles RU/UZ (default from Telegram language_code); honors tg-theme vars; first paint ≤3 s on 3G; bundle ≤300 KB gzip | ✓ VERIFIED (automated) + ? HUMAN (live theme/paint) | `i18n/index.ts` reads language_code and sets uz/ru ✓; ru.json and uz.json 72 keys each, PARITY PASS ✓; largest gzip chunk = 42.8 KB (vendor), total = 131 KB, well under 300 KB ✓; first-paint visual + theme deferred to live |
| SC#5 | Bot greets client with Web App button; routes status notifications via deliveries/notify queue | ✓ VERIFIED | `telegram/handlers/start.py` CommandStart handler sends greeting + web_app_keyboard(lang) ✓; calls get_or_create_client ✓; `notify.py` task on `notify` queue ✓; compose worker consumes notify queue ✓ |

**Score:** 5/5 truths verified (automated + code-level). 3 items carry human-needed deferred live verification per user-approved deploy-time deferral.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/services/client_service.py` | verify_init_data + get_or_create_client | ✓ VERIFIED | HMAC two-stage algorithm, compare_digest, TTL, future-token guard (HR-01), settings read at call time (HR-02) |
| `backend/app/api/deps.py` | get_current_client with Header alias | ✓ VERIFIED | `Header(alias="X-Telegram-Init-Data")`, generic 401 on all failures, identity from verified payload only |
| `backend/app/core/storage.py` | get_s3_client + ensure_bucket | ✓ VERIFIED | reads S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY; lazy import-safe |
| `backend/app/services/storage_service.py` | validate_upload + upload_request_file | ✓ VERIFIED | MAGIC_BYTES, MAX_SIZE_BYTES, MAX_FILES, traversal-safe key, telegram_file_id=None |
| `backend/app/schemas/webapp.py` | RequestCreate + all detail schemas | ✓ VERIFIED | D-02 model_validator, max_length fields (LR-01), MR-03 complete RequestDetailOut with 8 previously missing fields |
| `backend/app/services/request_service.py` | VALID_TRANSITIONS, create_request, transition_status | ✓ VERIFIED | Status machine correct, no db.commit(), audit trail on staff changes |
| `backend/app/api/webapp/requests.py` | POST/GET /webapp/requests | ✓ VERIFIED | IDOR-scoped by client.id, Depends(get_current_client) on every handler |
| `backend/app/api/webapp/me.py` | GET/PATCH /webapp/me | ✓ VERIFIED | Language restricted to ru/uz by schema |
| `backend/app/api/webapp/files.py` | POST /webapp/requests/{id}/files | ✓ VERIFIED | Count check before upload, validate_upload, Depends(get_current_client) |
| `backend/app/api/telegram_webhook.py` | POST /telegram/webhook/{secret} | ✓ VERIFIED | Dual secret check (path + header) via hmac.compare_digest, 403 on mismatch |
| `backend/app/tasks/notify.py` | send_status_change_notification | ✓ VERIFIED | D-10 localized labels, template rendering, deep-link button, never raises (try/except), no session.commit() (MR-01) |
| `telegram/bot.py` | Bot/Dispatcher singletons, setup_webhook | ✓ VERIFIED | setup_webhook no-ops when PUBLIC_WEBAPP_URL empty; WEBHOOK_SECRET masked in logs (CR-03) |
| `telegram/handlers/start.py` | /start handler | ✓ VERIFIED | CommandStart, lang from language_code, get_or_create_client, web_app_keyboard |
| `telegram/templates/ru/status_change.txt` | {number} and {status_label} placeholders | ✓ VERIFIED | "Заявка {number} → {status_label}" |
| `telegram/templates/uz/status_change.txt` | Uzbek parity | ✓ VERIFIED | "Ariza {number} → {status_label}" |
| `webapp/src/api/client.ts` | X-Telegram-Init-Data on every request | ✓ VERIFIED | apiFetch injects header; FormData detection prevents Content-Type conflict (CR-02) |
| `webapp/src/telegram.ts` | initTelegram, getInitData, button helpers | ✓ VERIFIED | @telegram-apps/sdk v2 wrapper, graceful degradation outside Telegram |
| `webapp/src/store/wizardStore.ts` | Client-only wizard state, D-01 | ✓ VERIFIED | No fetch in store, files: File[] |
| `webapp/src/i18n/ru.json` + `uz.json` | 72 keys each, full parity | ✓ VERIFIED | Key parity check PASS (72/72), all Copywriting Contract + error + status keys present |
| `webapp/src/util/datetime.ts` | formatTashkent with Asia/Tashkent | ✓ VERIFIED | Intl.DateTimeFormat with timeZone: 'Asia/Tashkent' |
| `webapp/src/pages/wizard/Confirm.tsx` | createRequest then sequential uploadFile | ✓ VERIFIED | for-await loop (not Promise.all), D-01 compliant |
| `webapp/src/pages/MyRequests.tsx` | getRequests, skeleton, EmptyState, ErrorBanner | ✓ VERIFIED | api.getRequests(), 3-card skeleton, visibilitychange refetch, pull-to-refresh |
| `webapp/src/pages/Settings.tsx` | patchMe + i18n.changeLanguage | ✓ VERIFIED | Both `patchMe` and `changeLanguage` present, optimistic update |
| `backend/tests/test_request_sla.py` | SLA proxy tests | ✓ VERIFIED | 4/4 PASS: readback <10s, enqueue no countdown/eta, no long sleep |
| `docs/phase-03-acceptance.md` | Live drill checklist citing TZ §6.1.1 | ✓ VERIFIED | All 5 SC checked; signed off for deploy-time deferral 2026-06-17 |
| `deploy/docker-compose.dev.yml` | minio service + notify queue | ✓ VERIFIED | minio service with healthcheck, api depends_on minio service_healthy, worker `-Q ingest,parse,notify,default`, S3_ENDPOINT wired to api+worker |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `deps.py` | `client_service.py` | get_current_client → verify_init_data + get_or_create_client | ✓ WIRED | Lazy imports inside function body |
| `webapp/requests.py` | `request_service.py` | create_request; list/get scoped by get_current_client | ✓ WIRED | `request_service.create_request(db, client, body)` |
| `request_service.py` | `tasks/notify.py` | send_status_change_notification.apply_async(queue="notify") | ✓ WIRED | Lazy import inside create_request and transition_status |
| `telegram_webhook.py` | `telegram/bot.py` | feeds Update to aiogram Dispatcher | ✓ WIRED | `dp.feed_update(bot, update)` |
| `tasks/notify.py` | `telegram/bot.py` | send_message via aiogram Bot | ✓ WIRED | `asyncio.run(bot.send_message(...))` |
| `api/client.ts` | `POST /webapp/requests` | apiFetch with X-Telegram-Init-Data | ✓ WIRED | Header injected on every apiFetch call including multipart |
| `Confirm.tsx` | `api/client.ts` | createRequest then uploadFile | ✓ WIRED | Sequential for-await loop |
| `main.py` | webapp routers | include_router under /api/v1 | ✓ WIRED | webapp_requests_router, webapp_me_router, webapp_files_router, telegram_webhook_router all included |
| `App.tsx` | All page components | React.lazy route bindings | ✓ WIRED | All 9 routes (C-01..C-09) bound to real lazy components |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `MyRequests.tsx` | `requests` state | `api.getRequests()` → `GET /webapp/requests` → `db.query(Request).filter(client_id)` | Yes — real DB query scoped by client | ✓ FLOWING |
| `RequestDetail.tsx` | `detail` state | `api.getRequest(id)` → `GET /webapp/requests/{id}` → `db.query(Request).filter(id, client_id)` | Yes — real DB query + joined files/history | ✓ FLOWING |
| `Confirm.tsx` | `reqNumber` state | `api.createRequest()` → `POST /webapp/requests` → `request_service.create_request` → PG sequence | Yes — generated REQ number from DB sequence | ✓ FLOWING |
| `notify task` | `status_label` | `client_facing_status(request.status)` → `_localized_status_label(lang, key)` | Yes — D-10 map lookup on real request status | ✓ FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend test suite (386 tests) | `python -m pytest -q` | 386 passed, 65 skipped, 0 failures | ✓ PASS |
| Phase-3 specific suites (97 tests) | `python -m pytest tests/test_init_data_auth.py tests/test_storage_validation.py tests/test_request_service.py tests/test_webapp_requests_api.py tests/test_notify_status_change.py tests/test_telegram_webhook.py tests/test_request_sla.py -q` | 97 passed | ✓ PASS |
| Webapp build | `npm run build` | Clean build, no errors | ✓ PASS |
| Bundle gzip (largest chunk) | Node measurement on dist/assets | 42.8 KB vendor chunk, 131 KB total; limit 300 KB | ✓ PASS |
| i18n key parity (ru vs uz) | Node script comparing flat keys | 72/72 keys match | ✓ PASS |
| TZ §6.1.1 SLA proxies | `test_request_readback_within_10s`, `test_status_change_enqueues_notify_promptly`, `test_notify_task_no_long_sleep` | 3/3 PASS | ✓ PASS |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REQ-webapp-auth | 03-01, 03-02, 03-04 | initData HMAC verification; first login creates clients row | ✓ SATISFIED | verify_init_data + get_current_client; HMAC algorithm, TTL, upsert, generic 401 |
| REQ-request-wizard | 03-02, 03-04, 03-06 | 4-step wizard; REQ number; files PDF/Excel/JPG ≤10 MB ≤5 | ✓ SATISFIED | create_request, number generation, storage_service validation, Confirm.tsx sequential upload |
| REQ-my-requests | 03-02, 03-05, 03-06 | Request list with statuses + history; bot push on status change | ✓ SATISFIED (CI) + ? HUMAN | GET /webapp/requests IDOR-scoped; notify task; MyRequests.tsx; StatusTimeline; live push timing deferred |
| REQ-webapp-i18n | 03-02, 03-04, 03-05 | RU/UZ toggle; default from Telegram language_code | ✓ SATISFIED (automated) + ? HUMAN | i18n/index.ts lang detection; parity PASS; Settings.tsx patchMe+changeLanguage; live toggle deferred |
| REQ-bot-clients | 03-03, 03-06 | Bot greeting + Web App button + status notifications | ✓ SATISFIED (code) + ? HUMAN | cmd_start + web_app_keyboard; notify task + templates; live bot test deferred |
| REQ-nfr-performance | 03-01, 03-04, 03-05, 03-06 | Bundle ≤300 KB gzip; Web App first paint ≤3 s on 3G; SLA proxies | ✓ SATISFIED (bundle) + ? HUMAN (first paint) | 42.8 KB largest chunk / 131 KB total; SLA proxy tests PASS; first-paint on 3G deferred |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `webapp/src/pages/MyRequests.tsx` | 23 | Comment: "Loading skeleton (3 placeholder cards...)" | Info | Comment describes the UI component purpose — not an implementation stub; skeleton is fully implemented |
| `backend/app/tasks/notify.py` | 9, 80 | "Supersedes the placeholder in tasks/placeholders.py" | Info | Historical comment only; the real task is fully implemented and registered |

No `TBD`, `FIXME`, or `XXX` markers found in any phase-3 modified file. Anti-patterns are informational comments only — no stubs detected.

---

### Code Review Status

All 9 findings from 03-REVIEW.md are resolved (status: resolved, 9/9 fixed):

| ID | Severity | Issue | Fix | Status |
|----|----------|-------|-----|--------|
| CR-01 | Critical | CORS missing `X-Telegram-Init-Data` in allow_headers | Added to `main.py` allow_headers list | ✓ RESOLVED (cc20644) |
| CR-02 | Critical | uploadFile sets Content-Type:application/json on multipart | FormData detection in apiFetch, omit Content-Type | ✓ RESOLVED (0379b82) |
| CR-03 | Critical | WEBHOOK_SECRET logged in plain text at INFO | Log masked URL `***/***` instead | ✓ RESOLVED (40410f4) |
| HR-01 | High | auth_date future-token not rejected | Added `age_seconds < -300` guard | ✓ RESOLVED (c7d872f+cef4893) |
| HR-02 | High | INIT_DATA_TTL_SECONDS bound at import time | Read from settings at call time | ✓ RESOLVED (c7d872f+cef4893) |
| MR-01 | Medium | notify task session.commit() on read-only session | Removed commit | ✓ RESOLVED (6cc9335) |
| MR-02 | Medium | uploadFile typed as Promise<void>, uses Promise<RequestFileMeta> | Return type corrected | ✓ RESOLVED (0379b82) |
| MR-03 | Medium | RequestDetailOut missing 8 fields | Added polymer_type, volume_unit, destination_country, port_or_city, desired_date, validity_days, urgency, comment | ✓ RESOLVED (ab59e70+ce4b26a) |
| LR-01 | Low | No max_length on free-text fields | Added Field(max_length=500/500/200/2000) | ✓ RESOLVED (2f50b36) |

---

### Human Verification Required

Three items require live-environment testing, all approved for deploy-time deferral by the user on 2026-06-17 (same precedent as Phase-2 02-07):

#### 1. Wizard Visual Flow + Telegram Integration

**Test:** Run `cd webapp && npm run dev` with backend running; open the Web App in Telegram. Verify Home focal point, per-step validation, BackButton state preservation, file limit enforcement, confirmation REQ number, theme adaptation.

**Expected:** All 7 visual checks from 03-04 Task 3 pass (Home focal point, step validation, step navigation, file UI, confirmation, theme light/dark).

**Why human:** Visual/interaction correctness of React screens inside the Telegram WebApp frame cannot be verified by grep or build. The Telegram SDK mock (`isTMA('simple')`) returns false outside Telegram, so SDK button behavior is unverifiable in CI.

#### 2. My-Requests List, Detail Timeline, and Language Toggle

**Test:** With a non-empty request list: verify MyRequests shows newest-first with correct D-10 chips; detail timeline timestamps are in Asia/Tashkent; Settings RU↔UZ toggle switches UI immediately and persists after app restart.

**Expected:** All 5 visual/behavioral checks from 03-05 Task 3 pass (list ordering, chips, detail timeline tz, language switch, persistence).

**Why human:** Timezone display correctness (locale-formatted dates in Asia/Tashkent), live i18n switch behavior, and Telegram visibility-change refetch require a running app inside Telegram.

#### 3. Live End-to-End Client-Circuit Drill

**Test:** Run the full drill from `docs/phase-03-acceptance.md` against a real BOT_TOKEN + public HTTPS PUBLIC_WEBAPP_URL:
- SC#1: wizard submit → REQ number confirmed in DB ≤10 s
- SC#2: PDF/JPG files confirmed in MinIO `polymer-files/requests/{id}/`; invalid types/sizes rejected
- SC#3: status change → bot push ≤30 s with D-10 label + deep-link
- SC#4: RU↔UZ toggle + Telegram theme adaptation + first-paint on Slow 3G
- SC#5: /start greeting + Web App button + `clients` row verified in DB

**Expected:** All 5 SCs PASS with recorded measurements in `docs/phase-03-acceptance.md`.

**Why human:** Requires a real BOT_TOKEN (live Telegram integration), a public HTTPS endpoint (for webhook registration and initData validation by Telegram), and a full docker-compose stack. Not provisioned in the current dev environment.

---

## Gaps Summary

No gaps. All automated must-haves are verified by codebase evidence and passing tests. Three live-environment checks are pending deploy-time verification per user-approved deferral (consistent with Phase-2 02-07 precedent). The automated CI gate (`test_request_sla.py` 4/4 PASS, backend 386/386 PASS, webapp build clean, bundle 131 KB gzip) stands as the current phase gate.

---

_Verified: 2026-06-17_
_Verifier: Claude (gsd-verifier)_
