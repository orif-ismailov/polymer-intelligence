"""
Userbot package — Telethon/MTProto long-lived monitoring process.

This package is a standalone long-lived process (separate from api/worker/beat)
that subscribes to enabled telegram_channel sources, writes new messages to
raw_items via the existing immutable save_raw_items dedupe path, and emits a
Redis heartbeat for liveness monitoring.

Entry point:   python -m userbot.main
Compose service:  docker compose up userbot

Architecture (DEC-userbot-separate-process):
  - NOT a Celery task — Telethon's asyncio event loop is incompatible with
    Celery's multiprocessing model.
  - Reads the enabled channel list from Postgres every ~10 min without restart
    (USERBOT_CHANNEL_REREAD_SECONDS, default 600).
  - Writes a Redis heartbeat every USERBOT_HEARTBEAT_SECONDS (default 60).
  - The check_userbot_health Celery beat task (*/5) monitors the heartbeat and
    raises a deduped admin alert on silence >5 min.
"""
