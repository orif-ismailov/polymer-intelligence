---
phase: 03-client-circuit
plan: 03
subsystem: telegram-bot
tags: [telegram, aiogram, webhook, bot, notify, celery, deeplink, tdd]

# Dependency graph
requires:
  - phase: 03-client-circuit
    plan: 01
    provides: "get_or_create_client, settings.BOT_TOKEN/WEBHOOK_SECRET/PUBLIC_WEBAPP_URL"
  - phase: 03-client-circuit
    plan: 02
    provides: "request_service.client_facing_status, CLIENT_STATUS_MAP, Request+Client ORM, notify enqueue hook"
provides:
  - "telegram/bot.py: bot (aiogram Bot), dp (Dispatcher), setup_webhook(), web_app_keyboard(lang), load_template(lang, name)"
  - "telegram/handlers/start.py: /start handler — RU/UZ greeting + Web App button + client upsert"
  - "telegram/templates/{ru,uz}/{start,status_change}.txt: 4 localized message templates"
  - "backend/app/api/telegram_webhook.py: POST /api/v1/telegram/webhook/{secret} with dual-secret validation (T-03-11)"
  - "backend/app/tasks/notify.py: send_status_change_notification task on notify queue"
affects:
  - "03-05-webapp-my-requests (bot push sends deep-link to request detail)"
  - "03-06-ops (bot token + webhook secret wired through deploy/.env.example)"

# Tech tracking
tech-stack:
  added:
    - "aiogram==3.29.0 (installed in backend venv; was in pyproject.toml since 03-01 but not installed)"
  patterns:
    - "Lazy aiogram imports inside task/handler bodies — import-safe, no network socket at module load"
    - "setup_webhook() no-op guard: returns early if PUBLIC_WEBAPP_URL is empty (dev/CI safety)"
    - "hmac.compare_digest for both path secret AND header secret (T-03-11 defense in depth)"
    - "asyncio.run() bridge for sync Celery task calling async aiogram bot.send_message"
    - "TDD RED→GREEN: failing tests committed before implementation (task 2)"
    - "pythonpath=['.',  '..'] in pytest.ini_options so tests import telegram/ from repo root"

key-files:
  created:
    - "telegram/__init__.py (package marker)"
    - "telegram/handlers/__init__.py (package marker)"
    - "telegram/bot.py (Bot+Dispatcher singletons, setup_webhook, web_app_keyboard, load_template)"
    - "telegram/handlers/start.py (cmd_start — /start handler with RU/UZ + client upsert)"
    - "telegram/templates/ru/start.txt (Russian greeting)"
    - "telegram/templates/uz/start.txt (Uzbek greeting)"
    - "telegram/templates/ru/status_change.txt ({number}/{status_label} RU template)"
    - "telegram/templates/uz/status_change.txt ({number}/{status_label} UZ template)"
    - "backend/app/api/telegram_webhook.py (POST /api/v1/telegram/webhook/{secret})"
    - "backend/tests/test_telegram_webhook.py (5 tests — all green)"
    - "backend/tests/test_notify_status_change.py (7 tests — all green)"
  modified:
    - "backend/app/tasks/notify.py (added send_status_change_notification + D-10 label maps)"
    - "backend/app/main.py (include telegram_webhook_router + lifespan setup_webhook call)"
    - "backend/pyproject.toml (pythonpath=['.',  '..'] in pytest.ini_options)"

key-decisions:
  - "DEC-telegram-pythonpath: pythonpath=['.',  '..'] in pytest.ini_options so tests can import telegram/ from repo root (telegram/ is at repo root, sibling of backend/, per dev-spec §4.1)"
  - "DEC-asyncio-run-bridge: send_status_change_notification uses asyncio.run() to call async bot.send_message from a sync Celery task — avoids adding a new event loop dependency"
  - "DEC-dual-secret-check: webhook checks BOTH path secret AND X-Telegram-Bot-Api-Secret-Token header via hmac.compare_digest — defense in depth per T-03-11"
  - "DEC-webapp-url-hash-deeplink: deep-link uses /#/requests/{id} hash fragment (consistent with DEC-03-04-hashrouter from 03-04)"

requirements-completed: [REQ-bot-clients, REQ-nfr-performance]

# Metrics
duration: 8min
completed: 2026-06-16
---

# Phase 3 Plan 03: Telegram Bot + Notify Task Summary

**Aiogram 3 webhook bot (POST /api/v1/telegram/webhook/{secret}): /start RU/UZ greeting with persistent Web App button + client upsert; send_status_change_notification Celery notify task with D-10 localized labels and deep-link button**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-16T13:03:40Z
- **Completed:** 2026-06-16T13:11:40Z
- **Tasks:** 2 (Task 1: bot package; Task 2: webhook + notify + main.py wiring)
- **Files modified:** 13 (11 new, 2 modified)

## Accomplishments

- `telegram/` package created at repo root (sibling of `backend/`) per dev-spec §4.1
- `telegram/bot.py` provides `bot`/`dp` singletons, `load_template()` with RU fallback,
  `web_app_keyboard(lang)` localized inline button, `setup_webhook()` with empty-URL guard
- `/start` handler greets in RU/UZ, upserts clients row via `get_or_create_client`,
  replies with Web App inline button — no business logic in the handler itself
- 4 templates: `{ru,uz}/{start,status_change}.txt` — all use `{placeholder}` tokens (str.format)
- `telegram_webhook.py` validates BOTH path secret AND `X-Telegram-Bot-Api-Secret-Token`
  header via `hmac.compare_digest` — either mismatch → 403 (T-03-11)
- `send_status_change_notification` task: loads Request+Client, maps internal status to
  D-10 display key via `client_facing_status()`, localizes via `_LANG_LABEL_MAP` (RU/UZ),
  renders `status_change.txt`, sends via `bot.send_message` with deep-link button; returns
  error dict without raising (T-03-13)
- `main.py` mounts telegram webhook router under `/api/v1`; lifespan registers webhook
  in production only (guarded by `PUBLIC_WEBAPP_URL`)
- Full suite: 380 passed, 65 skipped (no regressions; was 368 before plan)

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Bot package: Bot/Dispatcher, /start, RU/UZ templates | 1690fd6 | 8 new files in telegram/ |
| 2 RED | Failing tests for webhook + notify (TDD RED) | 4b4e78f | test_telegram_webhook.py, test_notify_status_change.py, pyproject.toml |
| 2 GREEN | Webhook router, notify task, main.py wiring (TDD GREEN) | c4e3fb4 | telegram_webhook.py, notify.py, main.py |

## TDD Gate Compliance

Task 2 followed the required RED/GREEN cycle:
- Task 2 RED: `test(03-03)` commit 4b4e78f — 12 tests failing (404 for webhook, ImportError for task)
- Task 2 GREEN: `feat(03-03)` commit c4e3fb4 — all 12 tests passing
- No REFACTOR commit needed (implementation was clean on first write)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] aiogram was in pyproject.toml but not installed in venv**
- **Found during:** Task 1 (import-safety check of telegram.bot)
- **Issue:** `aiogram>=3.13.0` was added to pyproject.toml in 03-01 but the venv had not been updated. Importing `telegram.bot` raised `ModuleNotFoundError: No module named 'aiogram'`.
- **Fix:** `pip install aiogram` in the backend venv (version 3.29.0 installed — legitimate, already approved in 03-01 Task 0 gate).
- **Files modified:** venv only (not git-tracked)
- **Committed in:** Not a separate commit — venv install is not tracked by git

**2. [Rule 3 - Blocking] `telegram` package not importable from backend tests**
- **Found during:** Task 2 RED phase (test fixture tried `patch("telegram.bot.dp")`)
- **Issue:** The `telegram/` package lives at repo root but pytest runs from `backend/`. Python's sys.path did not include the repo root, so `import telegram` raised `ModuleNotFoundError`.
- **Fix:** Added `pythonpath = [".", ".."]` to `[tool.pytest.ini_options]` in `backend/pyproject.toml` so pytest adds both `backend/` and the repo root to `sys.path` at test collection time.
- **Files modified:** `backend/pyproject.toml`
- **Committed in:** 4b4e78f (Task 2 RED commit)

## Known Stubs

None. All modules wire real logic:
- `setup_webhook()` calls real Telegram Bot API (guarded by PUBLIC_WEBAPP_URL; no-op in test)
- `cmd_start` calls real `get_or_create_client` and real `Session(engine)`
- `send_status_change_notification` loads real ORM objects, renders real templates
- All 4 templates contain real copy in RU and UZ

## Threat Surface Scan

All threat surface introduced by this plan is covered by the plan's `<threat_model>`:

| Threat ID | Status |
|-----------|--------|
| T-03-11 (Spoofing — forged webhook) | Mitigated — dual hmac.compare_digest (path + header) in telegram_webhook.py |
| T-03-12 (Info disclosure — deep-link leaking another client's request) | Mitigated — deep-link targets recipient's own request.id; IDOR guard from 03-02 T-03-07 covers cross-client access |
| T-03-13 (DoS — notify task crashing worker) | Mitigated — task wrapped in try/except, returns error dict, never raises |
| T-03-14 (Tampering — secret in source) | Accepted/mitigated — WEBHOOK_SECRET loaded from .env only (config.py), never literal in source |

No new threat surface beyond what the plan's threat model documents.

## Self-Check: PASSED

Files exist:
- telegram/bot.py — FOUND
- telegram/handlers/start.py — FOUND
- telegram/templates/ru/start.txt — FOUND
- telegram/templates/uz/start.txt — FOUND
- telegram/templates/ru/status_change.txt — FOUND
- telegram/templates/uz/status_change.txt — FOUND
- backend/app/api/telegram_webhook.py — FOUND
- backend/tests/test_telegram_webhook.py — FOUND
- backend/tests/test_notify_status_change.py — FOUND

Commits exist:
- 1690fd6 — feat(03-03): add aiogram bot package
- 4b4e78f — test(03-03): add failing tests for webhook router and notify task (TDD RED)
- c4e3fb4 — feat(03-03): implement webhook router, notify task, and main.py wiring (TDD GREEN)

Acceptance criteria:
- grep -q "Dispatcher" telegram/bot.py → PASS
- grep -q "CommandStart" telegram/handlers/start.py → PASS
- grep -q "{number}" telegram/templates/ru/status_change.txt → PASS
- grep -q "{status_label}" telegram/templates/ru/status_change.txt → PASS
- grep -q "hmac.compare_digest" backend/app/api/telegram_webhook.py → PASS (2 occurrences)
- grep -q "send_status_change_notification" backend/app/tasks/notify.py → PASS
- grep -c "telegram" backend/app/main.py ≥ 1 → 5 PASS
- pytest tests/test_telegram_webhook.py tests/test_notify_status_change.py → 12 passed PASS
- pytest -q (full suite) → 380 passed, 65 skipped PASS
