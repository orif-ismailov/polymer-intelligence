# CLAUDE.md — userbot/

Scoped guidance for `userbot/` (the Telethon MTProto channel monitor). See the repo-root
`CLAUDE.md` for the big picture.

## What this is

A **long-lived process** (`python -m userbot.main`) that maintains a persistent Telethon/MTProto
connection to monitor enabled `telegram_channel` sources in real time. It is **NOT a Celery task**
(DEC-userbot-separate-process) — it runs as its own Docker `userbot` service with
`restart: unless-stopped`.

It is a **repo-root package** (like `telegram/`), mounted read-only into the container at
`/app/userbot`; the `app.*` modules it imports come from the backend image.

## Layout

| Path | Role |
|------|------|
| `main.py` | `run_userbot()` — connects, registers the NewMessage handler, runs three concurrent loops. |
| `channel_registry.py` | `load_enabled_channel_sources()` — reads enabled, test-passing channels from Postgres. |
| `heartbeat.py` | `write_heartbeat()` — Redis liveness key. |
| `session.py` | `build_client()` + the interactive one-time `TG_SESSION_STRING` generation flow. |

## How it works

Three `asyncio.gather` loops:
1. **NewMessage handler** — writes channel messages to `raw_items` via the immutable
   `save_raw_items()` dedupe path. Skips empty/media-only messages (G6 cost guard); captures
   `fwd_from` metadata for stale-repost detection; per-message try/except so one bad message never
   kills the loop.
2. **Heartbeat loop** — writes a Redis heartbeat every `USERBOT_HEARTBEAT_SECONDS` (default 60s).
   The backend `check_userbot_health` beat task raises a deduped admin alert on >5 min silence.
3. **Channel-reread loop** — re-reads the enabled channel list every `USERBOT_CHANNEL_REREAD_SECONDS`
   (default 600s) and swaps the NewMessage handler **without restarting** (ROADMAP SC#1).

## Notes specific to this package

- **Credentials**: `TG_API_ID`/`TG_API_HASH` (from my.telegram.org) + `TG_SESSION_STRING` generated
  once via `session.py`. All from `.env`, never source literals (T-05-05). Process raises a clear
  error at startup if the session is missing/expired.
- Only sources with `last_test_ok_at IS NOT NULL` are monitored (T-05-09).
- **FloodWaitError** is caught at the top level → sleep `e.seconds` then reconnect (polite rate,
  T-05-06). The customer bears Telegram's restriction risk (AI-SPEC §1b).
- Imports are **lazy inside `run_userbot()`** so importing the module (e.g. for `ast.parse` in tests)
  triggers no `Settings()` validation or DB/Redis connection.
- It only writes `raw_items`; **parsing into signals is the backend's `parse_telegram_item` task**,
  not this process.
