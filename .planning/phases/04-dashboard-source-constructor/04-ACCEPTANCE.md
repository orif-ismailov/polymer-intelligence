# Phase 4: Dashboard + Source Constructor — Acceptance Document

**Phase:** 04-dashboard-source-constructor  
**Requirements:** REQ-live-feed, REQ-purchase-requests, REQ-price-trends, REQ-alerts, REQ-bot-team, REQ-source-builder  
**Created:** 2026-06-18  
**Status:** Pending deploy-time verification (see Deferred Items)

---

## Summary

This document maps each of the 5 Phase-4 success criteria (SC#1–SC#5) to:
1. The **automated CI proxy** command that gates every PR now.
2. The **deploy-time live drill** step required to fully satisfy the criterion against real infrastructure.

The automated proxies provide confidence in correctness at the unit/integration level.  The live drill steps require a running `docker compose` stack and are deferred to deploy time per the project precedent established at Phase-2 (02-07) and Phase-3 (03-06) checkpoints.

---

## SC#1 — Live Feed (REQ-live-feed)

**Full criterion:** The team views the unified Live Market Feed (`v_live_feed`) with filters (period, product, type, source, urgency) that refresh without reload via SSE (30 s polling fallback); feed/table API responds ≤500 ms at up to 1M signals.

### Automated CI Proxy

```bash
# Unit tests: keyset pagination, filters, SSE endpoint
cd backend && pytest tests/test_feed_api.py tests/test_feed_sse.py -x -q

# Performance gate (requires Postgres with ~1M seeded rows):
cd backend && pytest tests/test_feed_performance.py -m performance -v
```

**Proxy coverage:**
- `test_feed_api.py` (11 tests): keyset pagination, filter pass-through, cursor advance, 401 guard
- `test_feed_sse.py` (5 tests): `text/event-stream` content-type, `X-Accel-Buffering: no` header, data frame format, 401 guard
- `test_feed_performance.py` (3 tests, `-m performance`): ≤500 ms at ~1M rows, no Seq Scan on keyset path, second-page cursor also ≤500 ms

### Deploy-Time Live Drill

1. Bring up the stack: `docker compose up`.
2. Log in to the dashboard as any staff user.
3. Open `/` (Live Market Feed). Confirm rows render with the correct columns.
4. Apply a filter (e.g., `period=7d`, `product=PP`). Confirm the table updates.
5. Keep the page open. Trigger a new signal insertion (e.g., via a test UZEX fetch task). Confirm a new row appears **without page reload** within 30 s (SSE path) or 30 s (polling fallback).
6. Run `cd backend && pytest tests/test_feed_performance.py -m performance` against the live Postgres instance. Confirm all 3 tests pass (≤500 ms assertion).

**Pass criteria:** All 6 steps succeed.

---

## SC#2 — Purchase Requests Master-Detail (REQ-purchase-requests)

**Full criterion:** On the Purchase Requests screen the team opens a request's detail card (details, files, AI block: score + target-vs-avg price), changes status, assigns an owner, and adds notes — every action writes to `audit_log`.

### Automated CI Proxy

```bash
cd backend && pytest tests/test_dashboard_requests.py -x -q
```

**Proxy coverage:**
- `test_dashboard_requests.py` includes:
  - `test_audit_trail`: verifies that status change, note, assign, and contact actions all write an `audit_log` row
  - `test_invalid_transition_returns_422`: status machine rejects illegal transitions (D-12)
  - `test_viewer_cannot_patch_request`: viewer → 403 (T-04-10)
  - `test_price_analysis_in_detail`: D-02 price analysis computed from `price_points`

Also covered by RBAC matrix:
```bash
cd backend && pytest tests/test_rbac_dashboard.py::TestPatchRequestsRBAC -x -q
```

### Deploy-Time Live Drill

1. Open `/requests`. Confirm the paginated table renders with all columns.
2. Open a specific request's detail (click a row). Confirm the right-side Sheet opens with: Request Details, Source Info, AI block (price analysis populated, AI score shows Phase-5 placeholder), Files list.
3. Change status to `in_review`. Confirm the status chip updates and an audit_log row exists (check via admin DB access or backend logs).
4. Assign the request to a staff user. Confirm the Assigned column updates.
5. Add a note. Confirm it appears in the activity timeline.
6. Click "Contact Buyer" (if `telegram_user_id` is set). Confirm the `tg://` deep link resolves.

**Pass criteria:** All 6 steps succeed; `audit_log` contains one row per action.

---

## SC#3 — Price Trends + Source Health (REQ-price-trends, REQ-sources-health)

**Full criterion:** The team views a price chart per product/market sourced from `price_points`, and sees per-source health (last fetch, consecutive failures) with enable/disable.

### Automated CI Proxy

```bash
cd backend && pytest tests/test_prices_api.py tests/test_source_wizard.py tests/test_source_health.py -x -q
```

**Proxy coverage:**
- `test_prices_api.py` (9 tests): auth guard, daily data ≤1yr, weekly downsampling >1yr, bound params (no SQLi)
- `test_source_wizard.py` (14 tests): GET /sources health list, POST create, POST /{id}/test, PATCH enable-gate (422 without test pass), pending stubs
- `test_source_health.py`: 3-consecutive-failure recording, `is_enabled` toggle

### Deploy-Time Live Drill

1. Open `/prices`. Confirm the product tabs render (PP, HDPE, LDPE, etc.).
2. Select a product/market with data in `price_points`. Confirm the Recharts line chart renders with the correct date range.
3. Toggle the date range control (30d → 180d → 1yr). Confirm the chart redraws.
4. Open `/sources`. Confirm the health table shows all sources with last_fetch_at, consecutive_failures columns.
5. Select an `html_table` source and click Disable. Confirm `is_enabled` turns to `false`.
6. Re-enable it. Confirm `is_enabled` returns to `true` (requires `last_test_ok_at IS NOT NULL`).

**Pass criteria:** All 6 steps succeed.

---

## SC#4 — Alert Rules + Team Delivery (REQ-alerts, REQ-bot-team)

**Full criterion:** The team builds an alert rule (product, volume/price threshold, urgency, channel); matches deliver to DM/group respecting Telegram rate limits via the `deliveries` queue.

### Automated CI Proxy

```bash
cd backend && pytest tests/test_alert_service.py -x -q
```

**Key proxy test:**
```bash
cd backend && pytest tests/test_alert_service.py::TestDeliveryDispatch::test_delivery_dispatch -x -v
```

**Proxy coverage:**
- `test_alert_service.py` (27 tests): JSONB predicate interpreter correctness (all 6 predicates: kind, product_id, volume_gte, urgency_in, source_kind, lead_score_gte), dedupe via `IntegrityError` catch, delivery dispatch to `notify` queue with correct `chat_id`, token-bucket 25 msg/s (D-09)
- `test_alert_service.py::test_no_eval_in_alert_service`: zero `eval(` calls (T-04-24 security scan)

Also RBAC coverage:
```bash
cd backend && pytest tests/test_rbac_dashboard.py::TestAlertRulesWriteAdminOnly -x -q
```

**Live delivery note:** The `test_delivery_dispatch` test mocks the Telegram bot send. Actual delivery to a real Telegram chat requires a live bot token and is deploy-time only.

### Deploy-Time Live Drill

1. Open `/alerts`. Confirm the alert feed and rule builder render.
2. Create a new rule: pick product PP, set `volume_gte: 50`, enter a real Telegram chat_id.
3. Enable the rule.
4. Trigger a matching signal (e.g., insert a signal with `product_id=1, volume=100, kind='offer'`).
5. Confirm a delivery appears in the `deliveries` table within 30 s.
6. Confirm the Telegram DM/group receives the notification.
7. Fire the same rule again — confirm dedupe: only one alert per `rule+entity` key (no duplicate DM).

**Pass criteria:** All 7 steps succeed; delivery respects the 25 msg/s token-bucket limit.

---

## SC#5 — No-Code Add-Source Wizard (REQ-source-builder / TZ §6.1.6)

**Full criterion (Phase-4 scope):** An admin adds a new public website AND a new Telegram channel through the add-source wizard with no developer: the form is auto-built from the adapter's `config_schema`, a Test shows a ≤10-row preview, the source cannot be enabled until a test passes, and its signals subsequently appear in the feed.

### SC#5 Cross-Phase Caveat (MANDATORY)

> **The "telegram-channel signals appear in feed" portion of SC#5 is a Phase-5/6 acceptance item — NOT a Phase-4 item.**
>
> Phase 4 delivers the `telegram_channel` wizard path as a **saved-pending** flow only:
> - An admin CAN configure and save a `telegram_channel` source via the wizard.
> - The source is saved with `is_enabled=False` and `last_test_ok_at=NULL` (pending state).
> - The Test step for `telegram_channel` always returns `ok=False, error="Available after Phase 5"` — the server-side enable-gate therefore prevents it from ever being enabled in Phase 4.
> - The source's signals will NOT appear in the feed until the Telethon userbot + LLM extraction engine land in **Phase 5** (REQ-telegram-monitoring / REQ-ai-extraction).
>
> Phase 4 delivers **website onboarding end-to-end** (`html_table` and `rss` adapters):
> - Admin configures → Test runs (live fetch+parse) → ≤10 preview rows shown → Enable becomes available → signals appear in feed.
>
> This caveat is documented in `04-CONTEXT.md §Cross-phase boundary note` and in the Phase-4 ROADMAP SC#5 row.

### Automated CI Proxy

```bash
cd backend && pytest tests/test_source_wizard.py -x -q
```

**Key proxy tests:**
```bash
# Enable-gate: source without passing test cannot be enabled
cd backend && pytest tests/test_source_wizard.py::test_enable_gate_returns_422_when_no_test_passed -v

# Pending source: telegram_channel saves as is_enabled=False / last_test_ok_at=NULL
cd backend && pytest tests/test_source_wizard.py::test_pending_source_is_saved_disabled -v
```

**Proxy coverage:**
- `test_source_wizard.py` (14 tests): GET /sources, POST create, POST /{id}/test (≤10 rows), PATCH enable-gate (422), pending stub for telegram_channel + llm_page
- `test_html_table_adapter.py` (7 tests): SSRF guard, parse from real HTML, column cap
- `test_rss_adapter.py` (7 tests): SSRF guard, RSS 2.0 parse, Atom 1.0, row cap

Also RBAC:
```bash
cd backend && pytest tests/test_rbac_dashboard.py::TestSourcesWriteAdminOnly -x -q
```

**Phase-5 proxy (future):** When Phase 5 ships the Telethon userbot + LLM extraction, the "signals appear in feed" portion of SC#5 will be verified by the Phase-5 acceptance gate.

### Deploy-Time Live Drill (TZ §6.1.6)

**Website source (end-to-end in Phase 4):**

1. Log in as admin. Open `/sources`. Click "Add Source".
2. Select "HTML Table" or "RSS Feed" from the adapter picker.
3. The form auto-generates from `GET /admin/source-types` → adapter's `config_schema`. Fill in: Name, URL (a real public page with a polymer price table or RSS feed).
4. Click "Run Test". Confirm:
   - Test returns `ok: true`.
   - Preview table shows ≤10 normalized signal-draft rows (product / grade / volume / price / currency / section / event_at).
5. Click "Enable". Confirm the source switches to `is_enabled=true`.
6. Trigger a fetch cycle (or wait for the beat schedule). Confirm new signals from this source appear in the Live Feed at `/`.

**Telegram channel (saved-pending in Phase 4):**

7. In the wizard, select "Telegram Channel". Fill in the channel config.
8. Click "Run Test". Confirm it returns `ok: false` with message "Available after Phase 5".
9. Confirm the Enable button remains disabled (the source cannot be enabled).
10. Confirm the source appears in the sources list with a "Pending activation (Phase 5)" badge.

**Enable-gate invariant (TZ §6.1.6):**

11. Find any source where `last_test_ok_at IS NULL`. Attempt to enable it via PATCH. Confirm 422 ("Source cannot be enabled until a test has passed").

**Pass criteria:** Steps 1–6 succeed (website end-to-end); steps 7–10 succeed (telegram pending); step 11 returns 422.

---

## Deploy-Time Live Drill Checklist

A condensed checklist for the acceptance run:

```
SC#1 — Live Feed
  [ ] Feed renders on /
  [ ] Filters work (period + product)
  [ ] New signal appears without reload (SSE / polling)
  [ ] pytest tests/test_feed_performance.py -m performance → 3 PASSED

SC#2 — Purchase Requests
  [ ] Request detail opens with AI block (D-01/D-02 placeholders visible)
  [ ] Status change → audit_log row written
  [ ] Assign + note → audit_log rows written
  [ ] Contact Buyer → tg:// deep link

SC#3 — Prices + Source Health
  [ ] Price chart renders for product/market with data
  [ ] Date range control redraws chart
  [ ] Source enable/disable toggles is_enabled

SC#4 — Alerts + Delivery
  [ ] Alert rule created with real chat_id
  [ ] Matching signal triggers delivery → DM/group received
  [ ] Dedupe: second match = no duplicate notification

SC#5 — Source Wizard
  [ ] html_table/rss: configure → Test → ≤10 preview rows → Enable → signals in feed
  [ ] telegram_channel: configure → Test returns ok=false → cannot enable → pending badge
  [ ] Enable-gate: source without passing test → 422

NOTE: "telegram-channel signals appear in feed" is a Phase 5/6 acceptance item.
```

---

## Deferred Deploy-Time UAT

Per the Phase-2 / Phase-3 precedent in `STATE.md` (see Deferred Items table), the live drill above is deferred to deploy time. The automated CI gate (backend suite passing, dashboard build green, RBAC matrix, performance test collecting) is the CI-time gate.

**Prerequisites for live drill:**
- Running stack: `docker compose up` (api, worker, beat, postgres, redis, nginx)
- At least one real signal source configured (UZEX or test html_table)
- A real Telegram bot token (`BOT_TOKEN` in `.env`) for SC#4 delivery
- A real Telegram `chat_id` for the alert rule test

This item is registered as a deferred deploy-time UAT in `STATE.md`:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| UAT / Phase 4 SC#1–SC#5 | Live dashboard drill: SC#1 feed+SSE, SC#2 request detail+audit, SC#3 prices+sources, SC#4 alert delivery, SC#5 website onboarding end-to-end + telegram pending. SC#5 caveat: telegram-channel signals appear in feed is Phase-5/6. Prerequisites: docker compose stack + BOT_TOKEN + chat_id. CI gate: backend suite 536 PASSED, dashboard build green, RBAC matrix 35 PASSED, performance test 3 collected (-m performance). | Pending — deploy-time UAT | 2026-06-18 |
