---
phase: 04-dashboard-source-constructor
verified: 2026-06-18T00:00:00Z
status: human_needed
score: 5/5
overrides_applied: 0
human_verification:
  - test: "Live feed refreshes without reload via SSE"
    expected: "A new signal insertion causes a new row to appear in the feed at / within 30 s, without a page reload"
    why_human: "SSE streaming behavior requires a running stack; grep cannot verify timing/push behavior end-to-end"
  - test: "Purchase Requests detail panel opens, all actions reflect state"
    expected: "Opening a request detail shows the Sheet; status/assign/note/contact each update the UI and write audit_log"
    why_human: "Detail panel slide-in, action round-trips, audit_log row confirmation require a running stack"
  - test: "Price chart renders with data and date-range controls work"
    expected: "Recharts LineChart renders for a product/market with real price_points data; toggling 30d→1yr redraws"
    why_human: "Chart rendering and interactivity require a browser + running backend with seeded data"
  - test: "Alert delivery to Telegram DM/group with rate-limit respect"
    expected: "Creating a rule with a real chat_id and triggering a matching signal results in a Telegram DM within rate limits"
    why_human: "Real Telegram bot delivery requires BOT_TOKEN + live chat_id + running worker"
  - test: "Add-source wizard end-to-end: html_table/rss configure → Test → Enable → signals in feed"
    expected: "Admin fills wizard form (auto-built from config_schema), Run Test returns ≤10 preview rows, Enable switches source to is_enabled=true, signals appear in feed"
    why_human: "End-to-end onboarding requires a running stack + a real public HTML/RSS URL"
  - test: "Telegram channel wizard saves as pending and Test returns Phase 5 message"
    expected: "Selecting telegram_channel in wizard → Test returns ok=false 'Available after Phase 5' → Enable button stays disabled → source appears with 'Pending activation (Phase 5)' badge"
    why_human: "Wizard UI flow requires a running browser session"
  - test: "Feed performance: GET /feed ≤500 ms at ~1M rows, no Seq Scan"
    expected: "pytest tests/test_feed_performance.py -m performance passes all 3 tests"
    why_human: "Performance test requires a live Postgres instance with ~1M seeded rows (-m performance flag)"
---

# Phase 4: Dashboard + Source Constructor — Verification Report

**Phase Goal:** The internal team has a live, filterable working surface — the flagship Purchase Requests master-detail, the unified feed, prices, alerts, and source management — and an admin can onboard new public sources with no developer and no code.

**Verified:** 2026-06-18
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Unified Live Market Feed over v_live_feed with filters, SSE refresh + 30s polling fallback, keyset feed API | VERIFIED | `backend/app/api/feed.py`: keyset SELECT FROM v_live_feed, ORDER BY event_at DESC id DESC, no OFFSET, 5 filter params bound. `feed_bus.py` publishes to `feed:new`. `useSSE.ts` has `new EventSource`, exponential backoff, `POLL_FALLBACK_MS = 30_000`. `LiveFeedTable.tsx` wires `useSSE('/api/v1/feed/stream', ...)` and calls `invalidateQueries(['feed'])`. `feed_stream` returns `text/event-stream` with `X-Accel-Buffering: no`. SSE auth via `access_token` query param. |
| 2 | Purchase Requests detail card (details, files, AI block: score + target-vs-avg price), status change, assign owner, add notes — every action writes audit_log | VERIFIED | `dashboard_requests.py`: GET/PATCH/POST actions all route through `request_service` and call `write_audit`; status only via `transition_status` (no direct `.status =` assignment). `price_analysis_service.compute_price_analysis` queries `price_points WHERE market='UZ'` for real D-02 analysis. `RequestDetailPanel.tsx` opens shadcn Sheet `side="right"`. `AiAnalysisBlock.tsx` renders real `price_analysis` with delta label and "AI analysis available after Phase 5" placeholder. `RequestActions.tsx` has `useMutation` for all actions, invalidates `['request', id]`. test_dashboard_requests.py (498 lines) covers audit trail, invalid transition 422, viewer 403. |
| 3 | Price chart per product/market from price_points + per-source health (last fetch, consecutive failures) with enable/disable | VERIFIED | `prices.py`: GET /prices/series queries `FROM price_points` with daily/weekly downsampling (>365 days → `date_trunc('week')`), bound params. `PriceChart.tsx`: Recharts `LineChart` wired to `/prices/series` via `useQuery`. `SourcesList.tsx`: renders `last_fetch_at`, `consecutive_failures`, enable/disable toggle. GET /sources uses `sa.text` SELECT that never touches `config` column. test_prices_api.py (221 lines) + test_source_health.py (441 lines, 13 tests). |
| 4 | Alert rule builder (product, volume/price threshold, urgency, channel); matches deliver via deliveries/notify queue with Telegram rate limits | VERIFIED | `alert_service.py`: hardcoded per-key interpreter (kind/product_id/volume_gte/urgency_in/source_kind/lead_score_gte), 0 `eval(` calls, dedupe via IntegrityError catch on `uq_alerts_dedupe_key`, `send_delivery.apply_async(queue="notify")`. `notify.py` has `send_delivery` task with `queue="notify"`, token-bucket `_BOT_GLOBAL_INTERVAL_S = 1/25`. `alert_rules.py`: GET/POST/PATCH with require_admin, condition validated against KNOWN_PREDICATE_KEYS, per-rule channels D-08. `RuleBuilder.tsx`: "Activates with Phase 5 AI" disabled field, chat_id textarea, posts to /alert-rules. test_alert_service.py (427 lines, 27 tests) covers all 6 predicates, dedupe, delivery dispatch with queue="notify". |
| 5 | Add-source wizard: auto-built form from config_schema, Test ≤10-row preview, cannot enable until test passes; html_table/rss end-to-end; telegram_channel/llm_page PENDING-only | VERIFIED | `sources.py`: PATCH enable-gate returns 422 when `last_test_ok_at IS NULL`; POST /sources/{id}/test sets `last_test_ok_at` only on `ok=True`. `HtmlTableAdapter.test()`: `is_safe_url()` before fetch, `TestResult(ok=True, sample_rows=rows[:10])`. `TelegramChannelAdapter.test()`: `TestResult(ok=False, error="Available after Phase 5")`. All 4 adapters self-register at import; main.py imports all 4 packages at startup. `AddSourceWizard.tsx` fetches `/admin/source-types`, calls `/sources/{id}/test`, renders ≤10 preview rows. `JsonSchemaForm.tsx` unwraps `anyOf:[T,null]` (Pitfall 4). `SourcesList.tsx` renders "Pending activation (Phase 5)" badge for pending types. test_source_wizard.py (501 lines) covers enable-gate 422, pending source, html_table test endpoint. |

**Score:** 5/5 truths verified (automated codebase evidence)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/api/feed.py` | GET /feed keyset + GET /feed/stream SSE | VERIFIED | FROM v_live_feed, keyset WHERE, no OFFSET, SSE StreamingResponse |
| `backend/app/core/feed_bus.py` | Redis pub/sub publish/subscribe | VERIFIED | FEED_CHANNEL = "feed:new", lazy import |
| `backend/app/schemas/dashboard.py` | FeedItem, FeedPage + all downstream schemas | VERIFIED | All schemas present |
| `backend/app/api/dashboard_requests.py` | GET/PATCH /requests + actions | VERIFIED | 564 lines, all actions, CSV export |
| `backend/app/services/price_analysis_service.py` | D-02 from price_points | VERIFIED | Queries price_points WHERE market='UZ' |
| `backend/app/services/request_service.py` | add_note, assign_owner, log_contact_buyer | VERIFIED | All 3 functions present |
| `backend/app/api/admin_users.py` | GET /admin/users admin-only | VERIFIED | sa.text SELECT, no password_hash |
| `backend/app/ingest/html_table/adapter.py` | Live adapter with SSRF guard, 10-row preview | VERIFIED | is_safe_url() before fetch, register_adapter |
| `backend/app/ingest/rss/adapter.py` | Live adapter with SSRF guard | VERIFIED | is_safe_url() before fetch, register_adapter |
| `backend/app/ingest/telegram_channel/adapter.py` | Pending stub, ok=False | VERIFIED | "Available after Phase 5", fetch returns [] |
| `backend/app/ingest/llm_page/adapter.py` | Pending stub, ok=False | VERIFIED | "Available after Phase 5", fetch returns [] |
| `backend/app/api/sources.py` | GET/POST/PATCH /sources + test with enable-gate | VERIFIED | enable-gate 422, config never in GET |
| `backend/app/services/alert_service.py` | evaluate_condition + evaluate_alert_rules | VERIFIED | Hardcoded interpreter, 0 eval(), dedupe, send_delivery dispatch |
| `backend/app/tasks/notify.py` | send_delivery Celery task, queue="notify", rate-limit | VERIFIED | queue="notify", token-bucket 25 msg/s |
| `backend/app/api/alert_rules.py` | GET/POST/PATCH /alert-rules + GET /alerts | VERIFIED | require_admin on writes, condition validated |
| `backend/app/api/prices.py` | GET /prices/series with downsampling | VERIFIED | price_points query, >365d weekly aggregate |
| `dashboard/hooks/useSSE.ts` | EventSource + backoff + 30s polling fallback | VERIFIED | new EventSource, POLL_FALLBACK_MS=30_000 |
| `dashboard/lib/api.ts` | Bearer fetch + 401 redirect | VERIFIED | Authorization header, /login redirect |
| `dashboard/lib/tz.ts` | Asia/Tashkent formatter | VERIFIED | TZ = "Asia/Tashkent" |
| `dashboard/components/layout/Sidebar.tsx` | 240px nav, token classes, no hex | VERIFIED | w-60 bg-background-secondary, 4 nav groups |
| `dashboard/app/(dashboard)/layout.tsx` | Auth guard + QueryClientProvider | VERIFIED | redirect to /login, QueryClientProvider |
| `dashboard/components/feed/LiveFeedTable.tsx` | TanStack table + SSE wiring | VERIFIED | ['feed'] query key, useSSE, feed/stream |
| `dashboard/components/feed/AiMarketSignalsPanel.tsx` | D-01 placeholder panel | VERIFIED | "after Phase 5", 3 placeholder rows |
| `dashboard/components/requests/RequestDetailPanel.tsx` | 400px Sheet side=right | VERIFIED | Sheet side="right", role="dialog" |
| `dashboard/components/requests/AiAnalysisBlock.tsx` | D-01/D-02 AI block | VERIFIED | real price_analysis + "after Phase 5" placeholder |
| `dashboard/components/requests/RequestActions.tsx` | All actions with useMutation | VERIFIED | Contact Buyer, status, assign, note, useMutation |
| `dashboard/components/sources/JsonSchemaForm.tsx` | anyOf unwrap + required[] | VERIFIED | resolveType() unwraps anyOf:[T,null] |
| `dashboard/components/sources/AddSourceWizard.tsx` | 4-step wizard, source-types, test, enable | VERIFIED | Fetches /admin/source-types, calls /test, "Run Test" |
| `dashboard/components/sources/SourcesList.tsx` | Health + pending badge | VERIFIED | "Pending activation (Phase 5)", last_fetch_at, consecutive_failures |
| `dashboard/components/alerts/RuleBuilder.tsx` | Full predicate set, disabled lead_score, chat_ids | VERIFIED | "Activates with Phase 5 AI" disabled, chat_id textarea |
| `dashboard/components/prices/PriceChart.tsx` | Recharts LineChart from /prices/series | VERIFIED | LineChart, /prices/series query |
| `backend/tests/test_feed_api.py` | Keyset pagination + filter tests | VERIFIED | 289 lines |
| `backend/tests/test_feed_sse.py` | SSE content-type + headers | VERIFIED | 163 lines |
| `backend/tests/test_feed_performance.py` | ≤500 ms @ ~1M rows, @pytest.mark.performance | VERIFIED | Marker present, 500 ms assert, Seq Scan check |
| `backend/tests/test_dashboard_requests.py` | Status machine + audit trail | VERIFIED | 498 lines, write_audit patched in audit tests |
| `backend/tests/test_alert_service.py` | 27 tests, all 6 predicates, dedupe, dispatch | VERIFIED | 427 lines, TestDeliveryDispatch, test_no_eval, test_dedupe |
| `backend/tests/test_prices_api.py` | Range + downsampling + empty | VERIFIED | 221 lines |
| `backend/tests/test_source_wizard.py` | Enable-gate 422, pending, html_table test | VERIFIED | 501 lines, test_enable_gate_returns_422, test_pending_source |
| `backend/tests/test_rbac_dashboard.py` | Viewer 403, role matrix | VERIFIED | 448 lines, TestPatchRequestsRBAC, TestSourcesWriteAdminOnly, TestAlertRulesWriteAdminOnly |
| `.planning/phases/04-dashboard-source-constructor/04-ACCEPTANCE.md` | SC#1–SC#5 + SC#5 caveat | VERIFIED | All 5 SCs mapped, SC#5 caveat explicit |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `feed.py` | `v_live_feed` | sa.text keyset SELECT | VERIFIED | `FROM v_live_feed` confirmed |
| `main.py` | `feed_router` | include_router /api/v1 | VERIFIED | Line 139 in main.py |
| `feed.py` | `feed_bus.py` | subscribe_feed_events | VERIFIED | Imported at line 42 of feed.py |
| `main.py` | html_table/rss/telegram_channel/llm_page | import for self-registration | VERIFIED | Lines 46-49 in main.py |
| `dashboard_requests.py` | `request_service.transition_status` | PATCH calls service | VERIFIED | grep shows transition_status calls, 0 direct .status= assignments |
| `dashboard_requests.py` | `audit_service.write_audit` (via request_service) | every action writes audit | VERIFIED | all service functions call write_audit |
| `dashboard_requests.py` | `price_analysis_service.compute_price_analysis` | detail response embeds price_analysis | VERIFIED | line 73 of dashboard_requests.py |
| `alert_service.py` | `notify.send_delivery` | apply_async queue="notify" | VERIFIED | line 265, lazy import |
| `sources.py` | `ingest.registry.get_adapter` | test endpoint resolves adapter | VERIFIED | get_adapter called in test_source endpoint |
| `html_table/adapter.py` | `http_client.is_safe_url` | SSRF guard before fetch | VERIFIED | is_safe_url() called before fetch in test() |
| `AddSourceWizard.tsx` | `/api/v1/admin/source-types` | fetch config_schema → JsonSchemaForm | VERIFIED | queryKey ["source-types"], apiFetch |
| `AddSourceWizard.tsx` | `/api/v1/sources/{id}/test` | Run Test → preview rows | VERIFIED | apiFetch(`/sources/${createdSourceId}/test`) |
| `PriceChart.tsx` | `/api/v1/prices/series` | useQuery → LineChart | VERIFIED | apiFetch('/prices/series?...') |
| `LiveFeedTable.tsx` | `useSSE.ts` | useSSE('/api/v1/feed/stream', invalidate) | VERIFIED | useSSE import and `feed/stream` usage |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `LiveFeedTable.tsx` | `feedPage` (FeedPage) | GET /feed → v_live_feed (Postgres) | Yes — keyset SELECT on real view | FLOWING |
| `RequestDetailPanel.tsx` | `detail` (RequestDetailOut) | GET /requests/{id} → ORM + price_points | Yes — real Request + compute_price_analysis | FLOWING |
| `PriceChart.tsx` | `seriesData` (PriceSeriesOut[]) | GET /prices/series → price_points | Yes — real aggregate query | FLOWING |
| `AlertFeed.tsx` | `alerts` (AlertOut[]) | GET /alerts → Alert ORM | Yes — real Alert query | FLOWING |
| `SourcesList.tsx` | `sources` (SourceHealthItem[]) | GET /sources → sa.text SELECT | Yes — real sources rows | FLOWING |
| `app/(dashboard)/page.tsx` | KPI cards | Hardcoded "—"/0 (D-01 known placeholder) | No — intentional; real aggregation deferred | HOLLOW (intentional — D-01 non-blocking per orchestrator context) |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Feed router mounts at /api/v1/feed | `grep -n "feed_router\|prefix.*api/v1" backend/app/main.py` | Line 139: `include_router(feed_router, prefix="/api/v1")` | PASS |
| OFFSET absent from feed.py (keyset-only) | `grep -c "OFFSET" backend/app/api/feed.py` | 0 | PASS |
| eval() absent from alert_service.py | `grep -c "eval(" backend/app/services/alert_service.py` | 0 | PASS |
| password_hash absent from admin_users.py | grep check | Only in comments as "never expose" | PASS |
| send_delivery registered on notify queue | `grep -n "queue.*notify" backend/app/tasks/notify.py` | Line 255: `queue="notify"` | PASS |
| All 4 adapters imported in main.py | `grep "app.ingest.*" backend/app/main.py` | Lines 46-49 confirm all 4 | PASS |
| JsonSchemaForm anyOf unwrap present | `grep -n "anyOf" dashboard/components/sources/JsonSchemaForm.tsx` | resolveType() function at line 58 | PASS |
| test_alert_service.py has 27 tests | `grep -c "def test_" backend/tests/test_alert_service.py` | 27 | PASS |
| test_feed_performance.py has performance marker | `grep -n "performance" backend/tests/test_feed_performance.py` | @pytest.mark.performance at line 176 | PASS |
| No hardcoded hex in feed/requests/alerts/sources components | grep -rn "#[0-9a-fA-F]{6}" on those dirs | 0 results | PASS |

---

### Probe Execution

No `probe-*.sh` scripts declared for this phase. Automated CI proxies are the designated gate (see 04-ACCEPTANCE.md).

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|------------|-------------|-------------|--------|----------|
| REQ-live-feed | 04-01, 04-02, 04-03, 04-09 | Unified feed v_live_feed, SSE, keyset, filters | SATISFIED | feed.py + LiveFeedTable.tsx + useSSE verified |
| REQ-purchase-requests | 04-04, 04-05, 04-09 | Requests table + detail + actions + audit_log | SATISFIED | dashboard_requests.py + RequestDetailPanel + test_dashboard_requests.py |
| REQ-price-trends | 04-07, 04-08 | Price chart from price_points | SATISFIED | prices.py + PriceChart.tsx verified |
| REQ-alerts | 04-07, 04-08 | Alert rules builder + delivery | SATISFIED | alert_service.py + alert_rules.py + RuleBuilder.tsx verified |
| REQ-bot-team | 04-07 | Deliver to DM/group via notify queue, rate limits | SATISFIED | send_delivery with token-bucket 25 msg/s |
| REQ-source-builder | 04-06, 04-08, 04-09 | Admin onboards sources no-code, enable-gate | SATISFIED | sources.py + adapters + AddSourceWizard.tsx verified |
| REQ-sources-health | 04-06, 04-08 | Source health (last fetch, failures, enable/disable) | SATISFIED | GET /sources sa.text health query, SourcesList.tsx |

All 7 requirements (6 stated + REQ-sources-health which appears across plans) are covered with code evidence.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `dashboard/app/(dashboard)/page.tsx` | KPI cards | Hardcoded "—"/0 values | INFO (non-blocking) | Known D-01 placeholder per orchestrator context; SC#1-SC#5 do not depend on home KPI values |

No TBD/FIXME/XXX debt markers found in phase-modified files. No unresolved stubs in the critical path.

---

### Human Verification Required

#### 1. SSE Push Refresh (SC#1 live)

**Test:** Start the stack, log in, open `/`. Trigger a new signal insertion (test UZEX fetch or direct DB insert). Observe the feed.
**Expected:** New row appears without page reload within 30 s (SSE path) or within 30 s (polling fallback).
**Why human:** SSE timing behavior requires a running stack; grep cannot verify real-time event delivery.

#### 2. Purchase Requests Full Round-Trip (SC#2 live)

**Test:** Open a request detail. Change status to `in_review`. Assign to a staff user. Add a note. Click "Contact Buyer" (for a request with telegram_user_id set).
**Expected:** UI reflects each state change; `audit_log` contains one row per action (status, assign, note, contact).
**Why human:** Detail panel slide-in, round-trip mutations, and audit_log row confirmation require a running stack with data.

#### 3. Price Chart with Real Data (SC#3 live)

**Test:** Open `/prices`. Select a product/market combination that has price_points data. Toggle between 30d, 1yr, and a custom >1yr range.
**Expected:** LineChart renders with data; >1yr range uses weekly aggregated points (fewer, weekly intervals visible).
**Why human:** Chart rendering and interaction require a browser + running backend with seeded price_points.

#### 4. Alert Delivery to Telegram (SC#4 live)

**Test:** Create an alert rule with a real Telegram `chat_id`. Trigger a matching signal (product+volume threshold). Verify no duplicate DMs on second trigger.
**Expected:** DM arrives within 30 s; second identical trigger produces no duplicate notification (dedupe).
**Why human:** Real Telegram delivery requires BOT_TOKEN + live chat_id + running Celery worker on the notify queue.

#### 5. Add-Source Wizard End-to-End (SC#5 live — website path)

**Test:** Log in as admin. Open `/sources`, click "Add Source". Select "HTML Table" or "RSS Feed". Fill in a real public URL. Click "Run Test". After success, click "Enable".
**Expected:** Test shows ≤10 normalized preview rows. Enable switches source to `is_enabled=true`. Subsequent fetch cycle produces signals in the Live Feed.
**Why human:** End-to-end source onboarding with a real public URL requires a running stack + live HTTP fetch.

#### 6. Telegram Channel Wizard Pending Path (SC#5 live — telegram path)

**Test:** In the wizard, select "Telegram Channel". Fill in config. Click "Run Test".
**Expected:** Test returns `ok=false` with "Available after Phase 5" message. Enable button stays disabled. Source appears in list with "Pending activation (Phase 5)" amber badge.
**Why human:** Wizard UI flow and badge rendering require a browser session.

#### 7. Feed Performance Test at ~1M Rows (SC#1 NFR)

**Test:** `cd backend && pytest tests/test_feed_performance.py -m performance -v` against a Postgres instance with ~1M seeded signals rows.
**Expected:** All 3 performance tests pass: ≤500 ms first page, no Seq Scan on keyset path, second-page cursor also ≤500 ms.
**Why human:** Requires a live Postgres with sufficient data; the test skips without it.

---

### Gaps Summary

No BLOCKER gaps. All 5 success criteria have complete code evidence across backend + frontend:

- SC#1 (Live Feed): feed.py + feed_bus.py + LiveFeedTable.tsx + useSSE.ts fully wired; keyset-only (no OFFSET), SSE unbuffered, 30s polling fallback.
- SC#2 (Purchase Requests): dashboard_requests.py + request_service + price_analysis_service + RequestDetailPanel + AiAnalysisBlock + RequestActions fully wired; every action routes through service + audit.
- SC#3 (Prices + Source Health): prices.py + PriceChart.tsx + SourcesList.tsx + sources.py fully wired; weekly downsampling for >1yr confirmed.
- SC#4 (Alerts + Bot Delivery): alert_service.py (0 eval, hardcoded interpreter, dedupe, notify dispatch) + send_delivery (queue="notify", token-bucket 25 msg/s) + alert_rules.py + RuleBuilder.tsx.
- SC#5 (Source Wizard): sources.py enable-gate (422 without test pass) + four adapters + AddSourceWizard.tsx + JsonSchemaForm.tsx (anyOf unwrap) + SourcesList.tsx (pending badge); telegram_channel/llm_page permanently pending in Phase 4 per design.

7 deploy-time human verification items required (live stack + real data + real Telegram credentials). These are the same items documented in 04-ACCEPTANCE.md as deferred deploy-time UAT per Phase-2/3 precedent. The automated CI gate (backend suite 536 PASSED, dashboard typecheck/build green, RBAC matrix, alert interpreter, enable-gate, audit-trail tests) is fully satisfied.

---

_Verified: 2026-06-18_
_Verifier: Claude (gsd-verifier)_
