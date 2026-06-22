---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: executing
stopped_at: Completed 06-03-PLAN.md
last_updated: "2026-06-22T10:00:28.852Z"
last_activity: 2026-06-22 -- Phase 06 execution started
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 44
  completed_plans: 40
  percent: 83
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-13)

**Core value:** Every relevant market event lands accurately and quickly in a single normalized stream the team can see, filter, and act on — with no single source able to take the others down.
**Current focus:** Phase 06 — acceptance-handover

## Current Position

Phase: 06 (acceptance-handover) — EXECUTING
Plan: 3 of 7
Status: Ready to execute
Last activity: 2026-06-22 -- Phase 06 execution started

Progress: [██████████] 97%

## Performance Metrics

**Velocity:**

- Total plans completed: 27
- Average duration: -
- Total execution time: -

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02 | 7 | - | - |
| 03 | 6 | - | - |
| 04 | 9 | - | - |
| 05 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P02 | 19 | 2 tasks | 22 files |
| Phase 01 P04 | 25 | 2 tasks | 24 files |
| Phase 01 P03 | 10 | 2 tasks | 13 files |
| Phase 01 P05 | 8 minutes | 2 tasks | 3 files |
| Phase 01 P06 | 3min | 2 tasks | 3 files |
| Phase 01 P07 | 9min | 2 tasks | 6 files |
| Phase 01 P09 | 5min | 2 tasks | 2 files |
| Phase 01 P10 | 28min | - tasks | - files |
| Phase 02-ingest-core-uzex P01 | 7min | 2 tasks | 9 files |
| Phase 02 P02 | 25min | 2 tasks | 7 files |
| Phase 02-ingest-core-uzex P03 | 10min | 2 tasks | 10 files |
| Phase 02-ingest-core-uzex P05 | 13min | 2 tasks | 10 files |
| Phase 02-ingest-core-uzex P04 | 25min | 2 tasks | 11 files |
| Phase 02-ingest-core-uzex P06 | 8min | 2 tasks | 6 files |
| Phase 02-ingest-core-uzex P07 | ~35min | 2 tasks | 12 files |
| Phase 03-client-circuit P01 | 10min | 3 tasks | 10 files |
| Phase 03 P02 | 14min | 2 tasks | 9 files |
| Phase 03-client-circuit P04 | 90min | 4 tasks | 21 files |
| Phase 03 P05 | 60min | 3 tasks | 11 files |
| Phase 03 P06 | 25min | 3 tasks | 3 files |
| Phase 04 P01 | 15min | 2 tasks | 6 files |
| Phase 04 P02 | 8min | 2 tasks | 27 files created, 4 modified |
| Phase 04 P03 | 5min | 2 tasks | 10 files created, 1 modified |
| Phase 04 P04 | 20min | 2 tasks | 5 files created, 3 modified |
| Phase 04 P05 | ~15min | 3 tasks | 8 files created, 1 modified |
| Phase 04 P06 | ~15min | 2 tasks | 10 files created, 2 modified |
| Phase 04 P07 | 7min | 2 tasks | 8 files |
| Phase 04 P08 | 10min | 3 tasks | 10 files |
| Phase 06-acceptance-handover P02 | 25 min | 2 tasks | 2 files |
| Phase 06-acceptance-handover P03 | 3 min | 2 tasks | 1 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table (15 SPEC/DB technical decisions carried from ingest).
Most relevant to Phase 1:

- DEC-postgres-16: locked PG16 DDL — Phase 1 migration must reproduce it verbatim (schema contract: docs/polymer-intelligence-db-architecture.md)
- DEC-auth-split: JWT for dashboard (Phase 1) / Telegram initData for Web App (Phase 3)
- DEC-tz-handling: UTC in DB, Asia/Tashkent display — centralize in a helper from the start
- DEC-deploy-single-vps: docker compose container set (api, worker, beat, userbot, dashboard, postgres, redis, nginx)
- [Phase ?]: SQLAlchemy 2 requires explicit SA column types for timestamptz (DateTime(timezone=True)) and uses Float not Real
- [Phase ?]: synonyms table deferred to Phase 2 — locked DDL v1.1 has no synonyms table; synonyms.json seeded and ready for future migration
- [Phase ?]: nginx limit_req_zone rate=10r/m burst=5 nodelay on /api/v1/auth/login — closes ASVS L1 V2.2.1 at network layer (T-04-06)
- [Phase ?]: Tailwind design tokens in tailwind.config.ts — no hardcoded hex in dashboard components (REQ-nfr-security)
- [Phase ?]: Next.js output: standalone for Docker multi-stage build
- [Phase ?]: APP_ENV=production gates Secure cookie flag for refresh token (False dev/test, True prod TLS behind nginx)
- [Phase ?]: require_role reads role from verified JWT payload — no extra DB query needed for authorization
- [Phase ?]: Audit write uses db.flush() not db.commit() — caller commits, audit row shares transaction with audited action
- [Phase ?]: backend/Dockerfile added alongside deploy/Dockerfile.backend; nginx security headers re-declared in static-asset location to fix non-additive add_header drop (CR-06)
- [Phase 01-06]: Dashboard eslint CI command drops --ext flag (eslint 9 flat config rejects it; file matching comes from eslint.config.mjs)
- [Phase 01-06]: webapp/package-lock.json synced (@emnapi packages) as Rule 3 auto-fix so npm ci succeeds in CI
- [Phase 01-07]: CORS_ALLOWED_ORIGINS uses Union[list[str], str] field type so pydantic-settings v2 passes raw comma-separated env string to field_validator (list[str] alone triggers JSON decode failure)
- [Phase 01-07]: _DUMMY_HASH computed at module import time (not per-request); dummy_verify pays full argon2 KDF on every unknown-user login attempt to equalize timing with wrong-password path
- [Phase ?]: Keep S3_ENDPOINT: str = '' default in Phase 1 config.py — making it required breaks 100-passing suite; fail-fast validation deferred to Phase 2/3 S3 client construction
- [Phase ?]: CI S3 env contract test uses text-based parsing (no PyYAML dep) — regex check on ci.yml text is equivalent for asserting key presence
- [Phase ?]: ruff==0.15.17 and mypy==2.1.0 exact-pinned in [dev] for reproducible CI lint/type gate (UAT Gap 2 / SC#5)
- [Phase ?]: UP042: all 14 (str, enum.Enum) converted to enum.StrEnum — suite stayed green; B008 silenced via extend-immutable-calls for FastAPI DI; app.schemas.* disables disallow_any_explicit to avoid pydantic false positives
- [Phase ?]: No module-level synonym cache in match_product — DB query per call ensures admin-added rows are visible immediately (SC#4 admin-top-up-able)
- [Phase 02-04]: selectolax config-driven selectors: table_selector + columns list in source.config; no CSS selector literals in adapters.py (T-02-14)
- [Phase 02-04]: compute_content_hash uses ASCII Unit Separator (0x1F) between fields, whitespace-collapsed content; sha256 digest → immutable ON CONFLICT DO NOTHING dedup
- [Phase 02-04]: CAST(:payload AS JSONB) required for psycopg3 JSONB binding with raw SQL text()
- [Phase 02-04]: event_at parsing deferred to 02-05 signals write; adapters set event_at=None on all drafts
- [Phase ?]: product_text truncated to 512 chars before queue insert (T-02-05: DoS hardening against oversized UZEX cells)
- [Phase ?]: queue_for_classification uses ON CONFLICT(raw_item_id) DO NOTHING; never touches consecutive_failures — unrecognized goods are NOT source_failure (REQ-uzex-parser)
- [Phase 02-ingest-core-uzex]: DEC-source-adapter-registry: SourceAdapter is a typing.Protocol (runtime_checkable); adapters self-register by type_name at import time via register_adapter()
- [Phase 02-ingest-core-uzex]: DEC-ssrf-dns-resolution: is_safe_url() resolves hostname via socket.getaddrinfo() before HTTP activity; DNS failure = fail-safe reject; blocks loopback/private/link-local/reserved IPs and non-http(s) schemes (T-02-07)
- [Phase 02-ingest-core-uzex]: DEC-http-client-deferred-import: app.ingest.__init__.py omits http_client re-export to avoid triggering Settings() at pytest collection time; tests import directly from app.ingest.http_client inside function bodies
- [Phase 02-ingest-core-uzex]: DEC-no-code-flag: telegram_channel/llm_page/html_table/rss have no_code=True (Phase-4 wizard-addable); uzex_*/cbu_rates/sunsirs/dce have no_code=False (built-in specialized adapters)
- [Phase ?]: Grade regex extended for digit-leading polymer grade codes (2420D pattern)
- [Phase ?]: signal_service uses Mapping[str, object] for parsed arg (covariant) to satisfy strict mypy with dict[str, X] subtypes
- [Phase 02-06]: source_health_service uses db.flush() not db.commit() — caller commits (consistent with audit_service pattern)
- [Phase 02-06]: run_source_fetch_isolated: per-source try/except never re-raises — failure isolation SC#5/T-02-17/T-02-19; health service records success/failure
- [Phase 02-06]: dedupe_key source_failure:{source_id}:{date} + ON CONFLICT DO NOTHING — at most one source_failure alert per source per day (T-02-20)
- [Phase 02-07]: pg_backup.sh uses umask 077 + chmod 600 on dump files — closes T-02-23 (info-disclosure on world-readable backups)
- [Phase 02-07]: seed_sources: is_enabled=false + last_test_ok_at=NULL invariant enforced at seed time and verified in test — closes T-02-24
- [Phase 02-07]: signal_service comma-decimal price parsing: replace ',' before float() cast (Rule-1 auto-fix); UzexDealsAdapter section_label corrected to 'deals' (Rule-1 auto-fix)
- [Phase 02-07]: Accuracy harness uses pure-function path (parse_table_rows + create_signal_from_parse) with live-DB guard — CI-safe, no running DB needed; 100% on 55 positions = TZ §6.1.2 PASS
- [Phase 03-01]: DEC-lazy-s3-client: _LazyS3Client proxy defers boto3 import until first attribute access — keeps pytest collection socket-free when boto3 not installed in venv
- [Phase 03-01]: DEC-magic-byte-size-order: size check fires BEFORE magic-byte check in validate_upload — fast-path rejection for oversize files
- [Phase 03-01]: DEC-traversal-safe-key: S3 key = requests/{id}/{token_hex(8)}-{os.path.basename(filename)} — strips directory components + random token (T-03-06)
- [Phase 03-01]: DEC-generic-401: all initData failures → InvalidInitData (ValueError subclass) → get_current_client catches → generic 401 "Authentication required" (T-03-03)
- [Phase 03-01]: DEC-dep-owns-commit: get_current_client calls db.commit() after upsert; service functions use db.flush() only (caller commits pattern)
- [Phase ?]: DEC-lazy-notify-import: send_status_change_notification imported inside function bodies, test patches app.tasks.notify with create=True
- [Phase ?]: DEC-idor-opaque-404: cross-client request returns 404 not 403 (T-03-07 no information disclosure)
- [Phase ?]: DEC-per-date-postgres-sequence: REQ number via per-date PostgreSQL sequence, Asia/Tashkent date, concurrency-safe
- [Phase ?]: DEC-service-never-commits-confirmed: request_service uses db.flush() only; grep db.commit() returns 0
- [Phase ?]: DEC-03-04-hashrouter: HashRouter for Telegram Web App URL safety
- [Phase ?]: DEC-03-04-submit-deferred: Task 3 submit→REQ-number→confirmation path deferred to 03-06 E2E plan by user agreement (frontend-only scope verified)
- [Phase ?]: DEC-03-04-sequential-upload: Sequential file upload (for-await, not Promise.all) for 3G connection budget per D-01
- [Phase ?]: DEC-03-04-static-products: Product list hardcoded static constant (PP/HDPE/LDPE/LLDPE/PVC/PET/PS/ABS) — no GET /products endpoint in Phase 3
- [Phase ?]: DEC-03-05-optimistic-language: Settings switches UI immediately on toggle; PATCH failure shows ErrorBanner without reverting language
- [Phase ?]: DEC-03-05-backend-verify-deferred: backend-backed list/detail/timeline verification deferred to 03-06 E2E acceptance plan by user agreement at Task 3 checkpoint
- [Phase ?]: DEC-03-05-vite8-manualchunks: manualChunks uses function form for Vite 8/rolldown; vendor+i18n chunks split; largest gzip 42.8 KB (REQ-nfr-performance PASS)
- [Phase ?]: DEC-03-05-notifications-empty: Notifications C-08 shows EmptyState only in this phase — notification persistence is bot-side; screen exists as deep-link target per UI-SPEC C-08
- [Phase ?]: DEC-03-06-sla-gate: automated proxy tests (4/4 PASS) serve as CI gate; live wall-clock drill deferred to deploy time per user sign-off 2026-06-17
- [Phase ?]: DEC-03-06-rolled-deferral: live UI verifications from 03-04 (wizard submit path) and 03-05 (list/detail/timeline/refetch) roll into the same deploy-time SC#1/SC#3 drill
- [Phase ?]: DEC-04-01-route-no-trailing-slash: feed.py route path='' avoids FastAPI 307 redirect on /api/v1/feed
- [Phase ?]: DEC-04-01-lazy-redis-import: redis.asyncio imported inside function bodies in feed_bus.py — module import stays socket-free for pytest (mirrors request_service.py convention)
- [Phase 04-02]: DEC-shadcn-v4-tw3-compat: shadcn@4.11.0 generates Tailwind v4 CSS syntax (--spacing(), OKLCH, tw-animate-css imports); project uses Tailwind v3 — globals.css reverted to hsl() vars, card.tsx uses direct spacing classes, calendar.tsx uses fixed rem value
- [Phase 04-02]: DEC-jwt-memory-only: JWT access token stored in module-level variable via setToken/getToken in lib/api.ts — never localStorage, never DOM (T-04-06)
- [Phase 04-02]: DEC-sse-ref-useeffect: useSSE onMessage ref update moved to useEffect per react-hooks/refs — avoids render-time ref mutation warning
- [Phase 04-04]: DEC-04-04-contact-409: contact_buyer endpoint returns HTTP 409 when telegram_user_id IS NULL — semantically correct (state conflict: buyer exists but cannot be reached via Telegram) (D-11/Pitfall 6)
- [Phase 04-04]: DEC-04-04-status-as-string: RequestListOut/RequestDetailOut serialize status/urgency/incoterms as .value strings in router to avoid Pydantic from_attributes enum issues in mock-DB tests
- [Phase 04-04]: DEC-04-04-price-analysis-market-uz: compute_price_analysis hardcodes market='UZ' per RESEARCH Pattern 7; currency param is informational, price_points stores its own currency
- [Phase 04-05]: DEC-04-05-page-use-client: requests/page.tsx uses 'use client' because Lucide icon components cannot be passed as function props from Server Components to Client Components (Next.js App Router constraint)
- [Phase 04-05]: DEC-04-05-kpi-stubs: /requests page KPI cards all show '—' — no aggregate KPI endpoint exists for /requests in Phase 4; card shapes are final (D-01 contract)
- [Phase 04-05]: DEC-04-05-region-source-stubs: Region and Source columns in RequestsTable return '—' — RequestListOut schema from 04-04 does not include these fields; column structure matches UI-SPEC
- [Phase 04-06]: DEC-04-06-stdlib-rss: stdlib xml.etree.ElementTree used for RSS/Atom parsing — avoids feedparser dependency per T-04-SC; handles RSS 2.0 and Atom 1.0
- [Phase 04-06]: DEC-04-06-lazy-ssrf-proxies: is_safe_url/fetch_url imported as module-level lazy proxy functions in adapters — stable patch targets for tests while maintaining DEC-http-client-deferred-import
- [Phase 04-06]: DEC-04-06-registry-isolation: test fixtures use _reg._REGISTRY direct dict access for re-population after _clear_registry() — avoids 'already registered' ValueError from module cache
- [Phase 04-06]: DEC-04-06-asyncio-run: asyncio.run() replaces asyncio.get_event_loop().run_until_complete() in tests — Python 3.14 no longer auto-creates event loop in main thread
- [Phase 04-07]: DEC-04-07-lazy-patch-at-source: send_delivery lazy imported inside evaluate_alert_rules body — tests patch at app.tasks.notify.send_delivery (source module), not app.services.alert_service.send_delivery (no module-level attribute)
- [Phase 04-07]: DEC-04-07-no-eval-in-docstring: alert_service.py docstrings avoid literal "eval(" string to pass T-04-24 source-scan test (test_no_eval_in_alert_service reads file as text)
- [Phase 04-07]: DEC-04-07-weekly-aggregate-sql: prices.py selects daily vs weekly SQL branch by (date_to - date_from).days > 365 in router; weekly uses date_trunc('week') GROUP BY per dev-spec §3.1
- [Phase 04-07]: DEC-04-07-send-delivery-commits: send_delivery Celery task calls session.commit() (unlike service-layer flush-only); task is its own transaction boundary in Celery worker context
- [Phase 06-acceptance-handover]: DEC-06-02-disposable-fresh-container: fresh tmpfs postgres:16-alpine container is the clean-server restore target; dev volume is read-only source, never dropped — Proves the restore procedure end-to-end without risking the dev data volume (T-06-04)
- [Phase 06-acceptance-handover]: DEC-06-02-restore-from-file-not-pipe: pg_restore --jobs reads a docker cp'd file path, never stdin; runbook §3 corrected — Parallel restore cannot read from stdin (real gap surfaced by the drill)
- [Phase 06-acceptance-handover]: DEC-06-02-pin-superuser-pi_user: runbook DROP/CREATE uses -U pi_user -d postgres — No separate 'postgres' role exists; pi_user is the bootstrap superuser
- [Phase 06-acceptance-handover]: 06-03: closed §6.1.6 telegram_channel slice with a key-free pytest module (real orchestrator + mocked seams), unblocking SC#5-caveat retirement in 06-07 — Proves enable-gate 422 + fixture-message→signal→v_live_feed deterministically with no real account

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- UZEX page layout is the top external risk (SPEC §10.1) — keep selectors in `sources.config`, not code (affects Phase 2).
- Userbot account-restriction risk borne by customer; account/API_ID/API_HASH must be provided before Phase 5.
- AI control samples (TZ §6.1.3) and synonyms/channel lists are customer-provided — gate Phase 5 acceptance on their delivery.

## Deferred Items

Phase-2 international-loop requirements are a planned follow-up milestone, registered in REQUIREMENTS.md but intentionally not mapped to any current-milestone phase.

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Walking skeleton | SC#1 worker+beat Celery startup — needs `app.tasks.celery_app` (built in Phase 2; beat schedule drives UZEX fetch there) | Deferred to Phase 2 | 2026-06-15 |
| UAT / Phase 2 SC#5 | Live docker-compose drill: worker/beat uptime, live UZEX fetch→signals, re-fetch dedupe, live FX import, 3-strike source_failure alert with isolation (SC#5 / TZ §6.1.4), restore-doc dry-run — user-approved deferral to deploy time (02-07 Task 3 checkpoint) | Pending — deploy-time UAT | 2026-06-16 |
| UAT / Phase 3 SC#1–SC#5 | Live client-circuit drill: SC#1 wizard submit→REQ number queryable ≤10 s, SC#2 files→MinIO, SC#3 status push ≤30 s, SC#4 RU/UZ toggle + theme + first paint, SC#5 /start greeting + notify queue — user-approved deferral to deploy time (03-06 Task 3 checkpoint, 2026-06-17). Also includes rolled-in 03-04 wizard submit path and 03-05 list/detail/timeline verifications. Prerequisites: real BOT_TOKEN, WEBHOOK_SECRET, public HTTPS PUBLIC_WEBAPP_URL. CI gate: test_request_sla.py 4/4 PASS. | Pending — deploy-time UAT | 2026-06-17 |
| International loop | REQ-international-feed (FR-3) | Future Milestone | 2026-06-13 |
| Web App content | REQ-webapp-news (FR-8) | Future Milestone | 2026-06-13 |
| Reports | REQ-reports (FR-18) | Future Milestone | 2026-06-13 |
| Counterparties | REQ-counterparty-linking | Future Milestone | 2026-06-13 |
| Alerts publishing | REQ-intraday-channel-alerts | Future Milestone | 2026-06-13 |

## Session Continuity

Last session: 2026-06-22T10:00:22.973Z
Stopped at: Completed 06-03-PLAN.md
Resume file: None
