---
phase: 05-telegram-monitoring-ai
plan: "02"
subsystem: userbot
tags:
  - telethon
  - mtproto
  - userbot
  - heartbeat
  - channel-registry
  - health-alert
  - compose-service
  - telegram-channel-adapter
dependency_graph:
  requires:
    - "backend/app/core/config.py (TG_API_ID, TG_API_HASH + new TG_SESSION_STRING)"
    - "backend/app/services/raw_pipeline.py::save_raw_items (immutable dedupe path)"
    - "backend/app/ingest/base.py::RawItemDraft (dataclass)"
    - "backend/app/tasks/schedule.py::BEAT_SCHEDULE (added check_userbot_health)"
    - "backend/app/tasks/celery_app.py (task_routes + autodiscover)"
    - "deploy/docker-compose.dev.yml (worker/beat service model)"
    - "userbot/heartbeat.py::HEARTBEAT_KEY (cross-module contract)"
  provides:
    - "userbot/__init__.py (package)"
    - "userbot/session.py::build_client() -> TelegramClient"
    - "userbot/channel_registry.py::load_enabled_channels(session) -> list[str]"
    - "userbot/channel_registry.py::load_enabled_channel_sources(session) -> list[tuple[int, str]]"
    - "userbot/heartbeat.py::HEARTBEAT_KEY / write_heartbeat / read_heartbeat"
    - "userbot/main.py::run_userbot() (async entrypoint)"
    - "backend/app/services/userbot_health_service.py::check_userbot_heartbeat"
    - "backend/app/services/userbot_health_service.py::USERBOT_SILENCE_SECONDS=300"
    - "backend/app/tasks/userbot_health.py::check_userbot_health (Celery task)"
    - "backend/app/ingest/telegram_channel/adapter.py (live test + fetch replacing Phase-4 stub)"
    - "deploy/docker-compose.dev.yml::userbot service (python -m userbot.main)"
  affects:
    - "backend/app/core/config.py (TG_SESSION_STRING, USERBOT_CHANNEL_REREAD_SECONDS, USERBOT_HEARTBEAT_SECONDS added)"
    - "backend/app/tasks/schedule.py (check_userbot_health on */5 beat)"
    - "backend/app/tasks/celery_app.py (check_userbot_health route to ingest queue)"
    - "deploy/.env.example (TG_SESSION_STRING [SECRET], reread/heartbeat vars)"
    - "backend/tests/test_beat_schedule.py (updated to include check_userbot_health)"
tech_stack:
  added:
    - "telethon>=1.36,<2.0 installed (1.44.0; pre-approved in checkpoint T0)"
    - "Telethon TelegramClient + StringSession (userbot/session.py)"
    - "Telethon events.NewMessage (userbot/main.py message handler)"
    - "Telethon errors.FloodWaitError (polite-rate compliance AI-SPEC §1b)"
  patterns:
    - "Lazy telethon import inside test()/fetch() methods (socket-free at import time, DEC-http-client-deferred-import)"
    - "Redis key with TTL for liveness signal (userbot:heartbeat)"
    - "ON CONFLICT (dedupe_key) DO NOTHING + session.flush() dedup pattern (mirrors source_health_service)"
    - "asyncio.gather for concurrent loops (message handler, heartbeat loop, channel-reread loop)"
    - "Celery task opening short-lived SessionLocal + redis client (mirrors check_source_health)"
key_files:
  created:
    - userbot/__init__.py
    - userbot/session.py
    - userbot/channel_registry.py
    - userbot/heartbeat.py
    - userbot/main.py
    - backend/app/services/userbot_health_service.py
    - backend/app/tasks/userbot_health.py
    - backend/tests/test_userbot_channel_registry.py
    - backend/tests/test_userbot_heartbeat.py
    - backend/tests/test_telegram_channel_adapter.py
  modified:
    - backend/app/core/config.py (TG_SESSION_STRING, USERBOT_CHANNEL_REREAD_SECONDS, USERBOT_HEARTBEAT_SECONDS)
    - backend/app/ingest/telegram_channel/adapter.py (live test + fetch; stub replaced)
    - backend/app/tasks/schedule.py (check_userbot_health on */5)
    - backend/app/tasks/celery_app.py (check_userbot_health routed to ingest queue)
    - deploy/docker-compose.dev.yml (userbot service added)
    - deploy/.env.example (TG_SESSION_STRING [SECRET], reread/heartbeat interval vars)
    - backend/tests/test_beat_schedule.py (updated expected keys to include check_userbot_health)
decisions:
  - "_MinimalSource proxy in userbot/main.py — save_raw_items only reads source.id; avoids full ORM hydration from a raw SQL row in the async event handler"
  - "Lazy telethon import inside adapter.test()/fetch() — keeps module import-time socket-free (no MTProto TCP at import)"
  - "asyncio.gather for three concurrent loops — message handler + heartbeat + channel-reread all run in the same event loop without threads"
  - "Channel-reread loop removes old handler and adds new one (client.remove_event_handler + add_event_handler) — Telethon does not support dynamic chat-set mutation on an existing handler"
  - "USERBOT_SILENCE_SECONDS=300 aligned with the */5 beat cadence (5 min check, 5 min silence threshold — first missed heartbeat triggers alert)"
  - "TG_SESSION_STRING defaults to empty string in Settings so api/worker/beat services can start without it; userbot raises a clear RuntimeError only at startup if empty"
metrics:
  duration: "~11 min"
  completed: "2026-06-18T12:58:57Z"
  tasks_completed: 2
  files_created: 10
  files_modified: 7
---

# Phase 5 Plan 02: Telegram Userbot + Health Alert + Live Adapter Summary

## One-Liner

Telethon/MTProto userbot package (session, channel registry, heartbeat, async message handler → save_raw_items), live telegram_channel adapter replacing Phase-4 stub, Redis heartbeat liveness path with deduped userbot_silent admin alert on */5 beat, and a separate userbot Docker compose service.

## What Was Built

### Checkpoint T0 — telethon package legitimacy (pre-approved)

Resolved: pre-approved by user before dispatch. `telethon==1.44.0` installed.
PyPI author: LonamiWebs (telethon.dev), canonical MTProto library, pin `>=1.36,<2.0` confirmed valid.
No typosquat. Proceed to install and use telethon.

### Task 1: Userbot process

**`userbot/` package** (new top-level monorepo package, peer of `backend/` and `telegram/`):

- **`userbot/__init__.py`**: Package docstring describing the long-lived monitoring process architecture.

- **`userbot/session.py`**: `build_client()` returns `TelegramClient(StringSession(settings.TG_SESSION_STRING), TG_API_ID, TG_API_HASH)`. Raises `RuntimeError` with a clear customer-facing message (naming the 3 env vars and the generation procedure) when `TG_SESSION_STRING` is empty. Docstring documents the one-time interactive login flow. `TG_SESSION_STRING` is NEVER a source literal (T-05-05).

- **`userbot/channel_registry.py`**: `load_enabled_channels(session) -> list[str]` and `load_enabled_channel_sources(session) -> list[tuple[int, str]]`. Both filter `adapter='telegram_channel' AND is_enabled=true AND last_test_ok_at IS NOT NULL` (T-05-09 enable-gate invariant from Phase 4).

- **`userbot/heartbeat.py`**: `HEARTBEAT_KEY="userbot:heartbeat"`, `write_heartbeat(redis)` sets the key to `time.time()` string with TTL=`USERBOT_HEARTBEAT_SECONDS*10`, `read_heartbeat(redis) -> float | None`.

- **`userbot/main.py`** (348 lines): `async run_userbot()` with:
  - Build and connect client; assert `is_user_authorized()` or raise with guidance.
  - On startup: load `load_enabled_channel_sources()`; subscribe `events.NewMessage` handler.
  - **Message handler**: extract text, skip empty/media-only (G6 cost guard), look up `source_id` from channel username, build `RawItemDraft` with `fwd_from` payload (D14 stale-repost detection: `is_forwarded`, `fwd_from_date`, `username`), call `save_raw_items(session, _MinimalSource(source_id), [draft])` inside short-lived `SessionLocal`, commit. Per-message `try/except` isolates failures (T-05-07).
  - **Heartbeat loop**: every `USERBOT_HEARTBEAT_SECONDS` call `write_heartbeat`.
  - **Channel-reread loop**: every `USERBOT_CHANNEL_REREAD_SECONDS` re-read `load_enabled_channel_sources()`, diff against current list, remove old handler and add new one with updated chat set (hot-reload without process restart — ROADMAP SC#1).
  - **FloodWaitError handling**: sleep `e.seconds` then reconnect (AI-SPEC §1b polite rate, T-05-06).
  - `if __name__ == "__main__": asyncio.run(run_userbot())`.

**Config additions** (`backend/app/core/config.py`):
  - `TG_SESSION_STRING: str = ""` (empty default allows api/worker/beat to start without it)
  - `USERBOT_CHANNEL_REREAD_SECONDS: int = 600`
  - `USERBOT_HEARTBEAT_SECONDS: int = 60`

**`.env.example` additions**: `TG_SESSION_STRING` marked `[SECRET]`, reread/heartbeat interval vars.

**Tests (21 passing)**:
  - `test_userbot_channel_registry.py`: 11 tests — load_enabled_channels returns two enabled usernames, excludes NULL usernames, SQL contains correct filter criteria (adapter/is_enabled/last_test_ok_at); load_enabled_channel_sources returns (int, str) tuples.
  - `test_userbot_heartbeat.py`: 10 tests — HEARTBEAT_KEY constant, write_heartbeat sets key with TTL, read_heartbeat round-trips float, returns None when absent, reads from correct key.

### Task 2: Live adapter + health alert + compose service + beat task

**`backend/app/ingest/telegram_channel/adapter.py`** — Phase-4 stub replaced:
  - `test(config)`: validates config → lazy-import Telethon → build `TelegramClient(StringSession(...))` → `connect()` → `get_entity(username)` → `iter_messages(limit=10)` → `TestResult(ok=True, sample_rows=[{external_id, text_excerpt, date}...])`. On any error (FloodWaitError, not authorized, channel not found, empty session string) returns `TestResult(ok=False, error=...)` so enable-gate keeps source disabled (T-05-09). Lazy import keeps module socket-free at import time.
  - `fetch(source)`: pulls up to `config.backfill_days` of history as `RawItemDraft` list (wizard/backfill path; live ingestion is userbot's job). Respects keyword filters. Populates fwd_from payload. Handles FloodWaitError gracefully.
  - Self-registration line preserved.

**`backend/app/services/userbot_health_service.py`**:
  - `USERBOT_SILENCE_SECONDS = 300`
  - `check_userbot_heartbeat(session, redis)`: reads `read_heartbeat(redis)`. If absent or stale >300s, inserts `source_failure` alert with `dedupe_key=userbot_silent:{utc_date}` via `ON CONFLICT (dedupe_key) DO NOTHING` + `session.flush()`. Mirrors `raise_source_failure_alert` dedupe pattern from `source_health_service.py` (T-05-08 / T-02-20).

**`backend/app/tasks/userbot_health.py`**: Celery task `check_userbot_health` opening `SessionLocal` + redis, calling `check_userbot_heartbeat`, committing.

**`backend/app/tasks/schedule.py`**: `check_userbot_health` added on `crontab(minute="*/5")`.

**`backend/app/tasks/celery_app.py`**: `check_userbot_health` routed to `ingest` queue.

**`deploy/docker-compose.dev.yml`**: `userbot` service added — `command: python -m userbot.main`, `restart: unless-stopped`, `depends_on: [postgres, redis]`, env includes `TG_API_ID/TG_API_HASH/TG_SESSION_STRING/REDIS_URL/DATABASE_URL`, volume mounts `../userbot:/app/userbot`. Separate from worker/beat (DEC-userbot-separate-process).

**Tests (45 passing total)**:
  - `test_telegram_channel_adapter.py`: 14 tests — test() returns ok=True with sample rows (mocked), ok=False on telethon error, ok=False on absent session string, sample_rows capped at 10, FloodWait returns ok=False, adapter self-registers, config_schema is TelegramChannelConfig, no "Available after Phase 5" stub. check_userbot_heartbeat: stale heartbeat inserts alert, absent heartbeat inserts alert, fresh heartbeat does NOT insert alert, dedupe_key format matches `userbot_silent:YYYY-MM-DD`, SQL contains ON CONFLICT DO NOTHING.
  - `test_beat_schedule.py`: updated to include `check_userbot_health` in required keys (Rule 1 auto-fix).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `get_registry` import in test_telegram_channel_adapter**
- **Found during:** Task 2 test run
- **Issue:** Test used `from app.ingest.registry import get_registry` but the registry module exports `get_adapter`, not `get_registry`.
- **Fix:** Changed to `from app.ingest.registry import get_adapter` — `get_adapter("telegram_channel")` correctly validates self-registration.
- **Files modified:** `backend/tests/test_telegram_channel_adapter.py`
- **Commit:** 571d5ba

**2. [Rule 1 - Bug] `test_all_five_keys_present` hardcoded set of 5 keys**
- **Found during:** Task 2 test run (regression check)
- **Issue:** The existing beat schedule test had `required_keys` hardcoded to exactly 5 entries. Adding `check_userbot_health` (a correct and required change per plan) caused the test to fail with an "Extra items in left set" assertion error.
- **Fix:** Updated `required_keys` to include `"check_userbot_health"` with a comment explaining the Phase 5 addition.
- **Files modified:** `backend/tests/test_beat_schedule.py`
- **Commit:** 571d5ba

### Pre-existing Failures (Out of Scope)

Two tests were failing before 05-02 changes and are NOT caused by this plan:
- `test_prices_api.py::TestPricesApiRoutes::test_prices_path_mounted` — route mounting issue for `/api/v1/prices`
- `test_source_wizard.py::test_sources_router_mounted` — route mounting issue for `/api/v1/sources`

These are documented in `deferred-items.md` (out of scope per deviation rules).

## Known Stubs

None. All code is wired:
- `userbot/main.py` calls `save_raw_items` (live pipeline)
- `userbot/channel_registry.py` queries `sources` table (live DB)
- `userbot/heartbeat.py` uses `time.time()` (live timestamp)
- `check_userbot_heartbeat` inserts real alerts (live DB)
- `TelegramChannelAdapter.test()` no longer returns "Available after Phase 5"

## Deferred Human Verification (UAT)

**Final checkpoint (Task 3) — End-to-end live userbot ingestion drill**

This drill requires customer-provided TG account/API credentials + session string + a live monitored channel. Per the plan's explicit deferral note and the project's established phase-2/3/4 UAT deferral pattern, the live drill is deferred to deploy time. All code and automated tests are complete; this is a deploy-time verification item.

**Verification steps (for UAT):**

1. With real `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_STRING` in `.env` and at least one enabled telegram_channel source (with passing test), run:
   ```bash
   docker compose -f deploy/docker-compose.dev.yml up userbot
   ```

2. Confirm the userbot connects, subscribes to enabled channel(s), and logs the heartbeat write (`userbot.heartbeat_written` structlog event every 60 s).

3. Post (or wait for) a message in a monitored channel; confirm a new row appears in `raw_items` with `parse_status='pending'` and the `fwd_from` payload populated for forwarded messages.

4. Enable a second channel in the admin dashboard; within ~10 min confirm the userbot picks it up WITHOUT process restart (channel-reread loop log: `userbot.channel_list_updated`).

5. Stop the userbot container; within ~5 min confirm a `userbot_silent` alert appears in the `alerts` table with `dedupe_key=userbot_silent:{today}`.

**Expected outcomes:**
- Raw items land in the DB with `parse_status='pending'`, ready for the LLM parse orchestrator (05-04).
- The `is_forwarded: true` + `fwd_from_date` payload is present on forwarded messages.
- Reread loop picks up new channels without restart (SC#1 invariant).
- Silence alert is raised within 5 min of userbot stop (T-05-08 invariant).

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`. All mitigations implemented:
- T-05-05: TG_SESSION_STRING loaded from settings only; never a source literal; deploy/.env.example marks `[SECRET]`; no hardcoded session string found in `git grep`.
- T-05-06: FloodWaitError caught + `sleep(e.seconds)` in both `userbot/main.py` and adapter.
- T-05-07: Per-message `try/except` in message handler; empty/media-only messages skipped before `save_raw_items`.
- T-05-08: Redis heartbeat + `check_userbot_health` */5 + `userbot_silent` deduped alert; `restart: unless-stopped` in compose.
- T-05-09: `load_enabled_channel_sources` and adapter.test() both enforce `last_test_ok_at IS NOT NULL` gate.

## Self-Check: PASSED

**Key files verified:**
- FOUND: userbot/__init__.py
- FOUND: userbot/session.py
- FOUND: userbot/channel_registry.py
- FOUND: userbot/heartbeat.py
- FOUND: userbot/main.py
- FOUND: backend/app/services/userbot_health_service.py
- FOUND: backend/app/tasks/userbot_health.py
- FOUND: backend/tests/test_userbot_channel_registry.py
- FOUND: backend/tests/test_userbot_heartbeat.py
- FOUND: backend/tests/test_telegram_channel_adapter.py

**Commits verified:**
- FOUND: 950476a (Task 1 — userbot process)
- FOUND: 571d5ba (Task 2 — live adapter + health alert + compose + beat)
