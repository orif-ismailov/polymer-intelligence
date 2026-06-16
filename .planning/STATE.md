---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: completed
stopped_at: Completed 02-07-PLAN.md (reliability hardening + accuracy closure — phase 2 execution-complete; live drill deferred to deploy)
last_updated: "2026-06-16T08:39:52.513Z"
last_activity: 2026-06-16
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 17
  completed_plans: 17
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-13)

**Core value:** Every relevant market event lands accurately and quickly in a single normalized stream the team can see, filter, and act on — with no single source able to take the others down.
**Current focus:** Phase 02 — ingest-core-uzex

## Current Position

Phase: 3
Plan: Not started
Status: Phase 2 execution-complete; Phase 3 (Client Circuit) is next
Last activity: 2026-06-16

Progress: [████████░░] 82% (Phase 2 done; Phase 3 begins)

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: -
- Total execution time: -

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02 | 7 | - | - |

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
| International loop | REQ-international-feed (FR-3) | Future Milestone | 2026-06-13 |
| Web App content | REQ-webapp-news (FR-8) | Future Milestone | 2026-06-13 |
| Reports | REQ-reports (FR-18) | Future Milestone | 2026-06-13 |
| Counterparties | REQ-counterparty-linking | Future Milestone | 2026-06-13 |
| Alerts publishing | REQ-intraday-channel-alerts | Future Milestone | 2026-06-13 |

## Session Continuity

Last session: 2026-06-16T00:00:00Z
Stopped at: Completed 02-07-PLAN.md (reliability hardening + accuracy closure — phase 2 execution-complete; live drill deferred to deploy)
Resume file: None
