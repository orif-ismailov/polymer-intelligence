---
phase: 04
slug: dashboard-source-constructor
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-17
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `04-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest 8.2+ (confirmed in `backend/pyproject.toml`) |
| **Framework (frontend)** | TypeScript `tsc --noEmit` + ESLint (no component test runner yet) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd backend && pytest tests/test_feed_api.py tests/test_alert_service.py tests/test_source_wizard.py tests/test_dashboard_requests.py -x -q` |
| **Full suite command** | `cd backend && pytest tests/ --tb=short` then `cd dashboard && npm run typecheck && npm run lint` |
| **Estimated runtime** | ~30–60 seconds (backend unit); performance test (`-m performance`) skipped without Postgres |

---

## Sampling Rate

- **After every task commit:** Run the quick run command above (feed + alerts + source-wizard + requests unit suites).
- **After every plan wave:** `cd backend && pytest tests/ -q && cd ../dashboard && npm run typecheck && npm run lint`
- **Before `/gsd-verify-work`:** Full backend suite green + `npm run typecheck` passes.
- **Max feedback latency:** ~60 seconds.

---

## Per-Task Verification Map

> Requirement-level rows from RESEARCH.md § Validation Architecture. Exact `{N}-PP-TT` task IDs and Threat Refs are wired by the planner into each PLAN.md `<acceptance_criteria>`; `File Exists` reflects Wave 0 status (all backend test files are net-new — see Wave 0 below).

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| REQ-live-feed | `GET /feed` keyset pagination ≤500 ms, filters work, cursor advances | unit (mock DB) | `pytest tests/test_feed_api.py -x` | ❌ W0 | ⬜ pending |
| REQ-live-feed | SSE endpoint emits `text/event-stream` + new entity IDs | unit (httpx async) | `pytest tests/test_feed_sse.py -x` | ❌ W0 | ⬜ pending |
| REQ-purchase-requests | Status machine: `new→viewed` auto on detail open; invalid transition rejected | unit | `pytest tests/test_dashboard_requests.py -x` | ❌ W0 | ⬜ pending |
| REQ-purchase-requests | All team actions write `audit_log` (status, note, assign, contact) | unit | `pytest tests/test_dashboard_requests.py::test_audit_trail -x` | ❌ W0 | ⬜ pending |
| REQ-purchase-requests | D-02 price analysis computed from `price_points` (no LLM) | unit | `pytest tests/test_price_analysis.py -x` | ❌ W0 | ⬜ pending |
| REQ-price-trends | `GET /prices/series` correct date range + downsampling | unit | `pytest tests/test_prices_api.py -x` | ❌ W0 | ⬜ pending |
| REQ-alerts | JSONB interpreter: matching/non-matching predicates; `lead_score_gte` never matches in Phase 4 | unit (90%+ per dev-spec §8) | `pytest tests/test_alert_service.py -x` | ❌ W0 | ⬜ pending |
| REQ-alerts | Alert dedupe: same rule+entity → one alert (`ON CONFLICT DO NOTHING`) | unit | `pytest tests/test_alert_service.py::test_dedupe -x` | ❌ W0 | ⬜ pending |
| REQ-bot-team | Delivery dispatched to `notify` queue with correct `chat_id` from `rule.channels` | unit (mock Celery) | `pytest tests/test_alert_service.py::test_delivery_dispatch -x` | ❌ W0 | ⬜ pending |
| REQ-source-builder | `POST /sources/{id}/test` (`html_table`) returns ≤10 parsed signal drafts | unit (httpx fixture) | `pytest tests/test_source_wizard.py::test_html_table_test -x` | ❌ W0 | ⬜ pending |
| REQ-source-builder | `PATCH /sources/{id}` `is_enabled=true` without passing test → 422 | unit | `pytest tests/test_source_wizard.py::test_enable_gate -x` | ❌ W0 | ⬜ pending |
| REQ-source-builder | `telegram_channel` wizard save → `is_enabled=false`, `last_test_ok_at=NULL` (pending) | unit | `pytest tests/test_source_wizard.py::test_pending_source -x` | ❌ W0 | ⬜ pending |
| REQ-nfr-performance | Feed API ≤500 ms at 1M simulated rows | integration (Postgres) | `pytest tests/test_feed_performance.py -x -m performance` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All backend test files for this phase are net-new — establish them before/with the first feature task in each area:

- [ ] `backend/tests/test_feed_api.py` — REQ-live-feed (keyset pagination, filters)
- [ ] `backend/tests/test_feed_sse.py` — REQ-live-feed (SSE event emission, `text/event-stream`)
- [ ] `backend/tests/test_dashboard_requests.py` — REQ-purchase-requests (status machine, audit trail)
- [ ] `backend/tests/test_price_analysis.py` — D-02 price analysis computation
- [ ] `backend/tests/test_prices_api.py` — REQ-price-trends (`GET /prices/series`)
- [ ] `backend/tests/test_alert_service.py` — REQ-alerts + REQ-bot-team (**dev-spec §8: 90%+ coverage of the JSONB predicate interpreter**)
- [ ] `backend/tests/test_source_wizard.py` — REQ-source-builder (test endpoint, enable gate, pending state)
- [ ] `backend/tests/test_html_table_adapter.py` — `html_table` adapter fetch + test
- [ ] `backend/tests/test_rss_adapter.py` — `rss` adapter fetch + test

**Existing tests to reuse as patterns:**
- `backend/tests/test_request_service.py` — mock DB pattern for state machines
- `backend/tests/test_admin_source_types.py` — TestClient pattern for admin-only endpoints
- `backend/tests/test_source_health.py` — invariant-enforcement test pattern

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSE refresh updates feed without reload | REQ-live-feed | Browser EventSource + live render; not unit-observable | Open `/` feed, trigger a new signal, confirm row appears without reload (≤30 s polling fallback) |
| Dark-theme tokens render with no hardcoded hex | REQ-source-builder / UI-SPEC | Visual; `tailwind.config.ts` tokens must drive shadcn CSS vars | After shadcn init, diff `globals.css` against existing tokens; visual smoke of each screen in dark theme |
| Add-source wizard auto-form renders from `config_schema` | REQ-source-builder | Form is generated from live `GET /admin/source-types`; visual correctness of `anyOf`/Optional fields | Add an `html_table` source via wizard → Test → enable end-to-end; confirm preview shows ≤10 normalized rows |
| Telegram delivery reaches a team chat | REQ-bot-team | Requires live bot token + chat_id; rate-limit timing | Author a rule with a real `chat_id`, fire a matching signal, confirm DM/group delivery within rate limits |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (9 backend test files above)
- [ ] No watch-mode flags in commands
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter once planner wires task IDs

**Approval:** pending
