"""
Telegram userbot entrypoint — long-lived MTProto monitoring process.

Run as:  python -m userbot.main

Architecture (DEC-userbot-separate-process):
  This is NOT a Celery task. It runs as its own Docker service (`userbot`)
  with restart: unless-stopped. It maintains a persistent Telethon/MTProto
  connection and handles new channel messages in real time.

Behaviour:
  - On startup: load the enabled channel list and subscribe a NewMessage handler.
  - Message handler: write new messages to raw_items via save_raw_items()
    (the existing immutable dedupe path). Skip empty/media-only messages (G6).
    Populate fwd_from payload for stale-repost detection (AI-SPEC §4b.4/D14).
    Isolate per-message errors so one bad message never kills the loop.
  - Heartbeat loop: write Redis heartbeat every USERBOT_HEARTBEAT_SECONDS.
  - Channel-reread loop: re-read the enabled channel list from Postgres every
    USERBOT_CHANNEL_REREAD_SECONDS and update subscribed chats WITHOUT restart
    (ROADMAP SC#1 "rereads the channel list every ~10 min without restart").
  - FloodWaitError: sleep e.seconds then continue (AI-SPEC §1b polite rate).

Security:
  T-05-05: TG_SESSION_STRING from settings, never a source literal.
  T-05-06: FloodWaitError caught + sleep — polite rate compliance.
  T-05-07: Per-message try/except; empty/media-only messages skipped.
  T-05-08: Redis heartbeat; restart: unless-stopped in compose.
  T-05-09: Only sources with last_test_ok_at IS NOT NULL are monitored.
"""

from __future__ import annotations

import asyncio
import datetime
import logging

import structlog

log = structlog.get_logger(__name__)


async def run_userbot() -> None:
    """Async entrypoint for the Telegram userbot process.

    Connects to Telegram, subscribes to enabled channels, and runs
    three concurrent loops:
      1. NewMessage event handler (writes to raw_items)
      2. Heartbeat loop (writes Redis liveness key)
      3. Channel-reread loop (hot-reloads channel list from Postgres)
    """
    # Import here so that importing this module in tests (for ast.parse) does
    # not trigger Settings() validation or Redis/DB connections.
    import redis as redis_lib  # noqa: PLC0415
    import sqlalchemy as sa  # noqa: PLC0415
    from telethon import TelegramClient, events  # noqa: PLC0415
    from telethon.errors import FloodWaitError  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.ingest.base import RawItemDraft  # noqa: PLC0415
    from app.domains.signals.source_models import Source  # noqa: PLC0415
    from app.domains.signals.raw_pipeline import save_raw_items  # noqa: PLC0415
    from userbot.channel_registry import load_enabled_channel_sources  # noqa: PLC0415
    from userbot.heartbeat import write_heartbeat  # noqa: PLC0415
    from userbot.session import build_client  # noqa: PLC0415

    # ── Build and connect client ───────────────────────────────────────────────
    client: TelegramClient = build_client()

    try:
        await client.connect()
    except Exception as exc:
        log.error("userbot.connect_failed", error=str(exc))
        raise

    if not await client.is_user_authorized():
        log.error(
            "userbot.not_authorized",
            hint=(
                "The session string is invalid or expired. "
                "Re-generate TG_SESSION_STRING following the procedure in userbot/session.py."
            ),
        )
        raise RuntimeError(
            "Telegram userbot is not authorized. "
            "Regenerate TG_SESSION_STRING — see userbot/session.py."
        )

    log.info("userbot.connected")

    # ── Redis client ───────────────────────────────────────────────────────────
    _redis = redis_lib.from_url(settings.REDIS_URL)

    # ── Load initial channel list ──────────────────────────────────────────────
    with SessionLocal() as session:
        channel_sources = load_enabled_channel_sources(session)

    # Map username -> source_id for fast lookup in the message handler.
    # username_map is a dict; it is updated by the reread loop without restart.
    username_map: dict[str, int] = {uname: sid for sid, uname in channel_sources}
    channel_usernames: list[str] = list(username_map.keys())

    log.info("userbot.channels_loaded", count=len(channel_usernames), channels=channel_usernames)

    # ── NewMessage handler ────────────────────────────────────────────────────
    # We register a handler with the initial channel list. When the reread loop
    # updates username_map, it also removes the old handler and adds a new one
    # with the updated list of chats.

    def _make_handler(current_username_map: dict[str, int]) -> object:
        """Create a NewMessage event handler closure over the current channel map.

        Returns the handler coroutine (not the registered event).
        """
        async def _on_new_message(event: events.NewMessage.Event) -> None:  # type: ignore[name-defined]
            """Handle a new message from a monitored Telegram channel.

            Writes to raw_items via save_raw_items() (immutable dedupe path).
            Skips empty/media-only messages (G6 cost guard).
            Isolates per-message errors so one bad message never kills the loop.
            """
            try:
                # ── Skip empty / media-only messages (G6 cost guard) ──────────
                text: str | None = event.message.message
                if not text or not text.strip():
                    log.debug(
                        "userbot.message_skipped",
                        reason="empty_or_media_only",
                        message_id=event.message.id,
                    )
                    return

                # ── Identify source via username ───────────────────────────────
                # event.chat.username is the channel username (without @)
                chat = await event.get_chat()
                channel_username: str | None = getattr(chat, "username", None)
                if not channel_username:
                    log.debug(
                        "userbot.message_skipped",
                        reason="no_username",
                        message_id=event.message.id,
                    )
                    return

                source_id = current_username_map.get(channel_username)
                if source_id is None:
                    # Channel not in our registry — possibly a stale subscription.
                    log.debug(
                        "userbot.message_skipped",
                        reason="unknown_channel",
                        channel=channel_username,
                        message_id=event.message.id,
                    )
                    return

                # ── Build RawItemDraft ─────────────────────────────────────────
                message = event.message
                external_id = str(message.id)

                # event_at: use message.date (UTC aware datetime from Telethon)
                event_at: datetime.datetime | None = message.date

                # fwd_from metadata (D14 / AI-SPEC §4b.4 stale-repost detection)
                fwd_from = message.fwd_from
                is_forwarded = fwd_from is not None
                fwd_from_date: str | None = None
                if fwd_from is not None and hasattr(fwd_from, "date") and fwd_from.date:
                    fwd_from_date = fwd_from.date.isoformat()

                payload: dict[str, object] = {
                    "is_forwarded": is_forwarded,
                    "fwd_from_date": fwd_from_date,
                    "username": channel_username,
                }

                draft = RawItemDraft(
                    external_id=external_id,
                    content=text.strip(),
                    payload=payload,
                    event_at=event_at,
                )

                # ── Persist via the immutable dedupe pipeline ─────────────────
                with SessionLocal() as db_session:
                    # WR-08: cheap existence check only (the previous SELECT
                    # pulled 8 columns whose values were discarded —
                    # _MinimalSource is built from the already-known source_id).
                    # Use a clean `import sqlalchemy as sa` instead of the
                    # obfuscated __import__("sqlalchemy", ...) call.
                    exists = db_session.execute(
                        sa.text("SELECT 1 FROM sources WHERE id = :id"),
                        {"id": source_id},
                    ).fetchone()

                    if exists is None:
                        log.warning(
                            "userbot.source_not_found",
                            source_id=source_id,
                            channel=channel_username,
                        )
                        return

                    # Build a minimal Source-like object for save_raw_items.
                    # save_raw_items only reads source.id — the rest is not needed.
                    source_obj = _MinimalSource(source_id)
                    inserted, _ = save_raw_items(db_session, source_obj, [draft])
                    db_session.commit()

                log.info(
                    "userbot.message_persisted",
                    source_id=source_id,
                    channel=channel_username,
                    message_id=external_id,
                    inserted=inserted,
                    is_forwarded=is_forwarded,
                )

            except Exception as exc:
                # Isolate per-message failures — never let one bad message
                # kill the userbot event loop (T-05-07).
                log.exception(
                    "userbot.message_handler_error",
                    error=str(exc),
                    message_id=getattr(event.message, "id", None),
                )

        return _on_new_message

    # Register the initial handler
    current_handler = _make_handler(username_map)
    client.add_event_handler(
        current_handler,
        events.NewMessage(chats=channel_usernames or None),
    )

    # ── Heartbeat loop ────────────────────────────────────────────────────────
    async def _heartbeat_loop() -> None:
        """Write Redis heartbeat every USERBOT_HEARTBEAT_SECONDS."""
        while True:
            try:
                write_heartbeat(_redis)
                log.debug("userbot.heartbeat_written")
            except Exception as exc:
                log.warning("userbot.heartbeat_error", error=str(exc))
            await asyncio.sleep(settings.USERBOT_HEARTBEAT_SECONDS)

    # ── Channel-reread loop ───────────────────────────────────────────────────
    async def _channel_reread_loop() -> None:
        """Re-read the enabled channel list every USERBOT_CHANNEL_REREAD_SECONDS.

        Updates the subscribed chat set WITHOUT restarting the process.
        Newly-enabled channels are added; removed ones are dropped.
        ROADMAP SC#1: "rereads the channel list every ~10 min without restart".
        """
        nonlocal current_handler, username_map, channel_usernames

        while True:
            await asyncio.sleep(settings.USERBOT_CHANNEL_REREAD_SECONDS)
            try:
                with SessionLocal() as session:
                    new_sources = load_enabled_channel_sources(session)

                new_username_map = {uname: sid for sid, uname in new_sources}
                new_usernames = list(new_username_map.keys())

                if new_usernames == channel_usernames:
                    log.debug("userbot.channel_reread_no_change", count=len(new_usernames))
                    continue

                added = set(new_usernames) - set(channel_usernames)
                removed = set(channel_usernames) - set(new_usernames)
                log.info(
                    "userbot.channel_list_updated",
                    added=list(added),
                    removed=list(removed),
                    total=len(new_usernames),
                )

                # Remove old handler and add new one with updated chat list
                client.remove_event_handler(current_handler)
                username_map = new_username_map
                channel_usernames = new_usernames
                current_handler = _make_handler(username_map)
                client.add_event_handler(
                    current_handler,
                    events.NewMessage(chats=new_usernames or None),
                )

            except Exception as exc:
                log.warning("userbot.channel_reread_error", error=str(exc))

    # ── FloodWait wrapper ─────────────────────────────────────────────────────
    # The Telethon client will automatically raise FloodWaitError on any MTProto
    # call that triggers rate limiting. We handle it at the top-level run loop
    # to sleep and continue rather than crashing.

    async def _run_with_flood_wait_handling() -> None:
        """Run the client until disconnected, handling FloodWaitError gracefully."""
        while True:
            try:
                await client.run_until_disconnected()
                # run_until_disconnected() returns normally on clean disconnect
                log.info("userbot.disconnected_clean")
                break
            except FloodWaitError as exc:
                wait_seconds = exc.seconds
                log.warning(
                    "userbot.flood_wait",
                    wait_seconds=wait_seconds,
                    message=(
                        f"Telegram rate-limited the userbot (FloodWaitError). "
                        f"Sleeping {wait_seconds}s before reconnecting. "
                        f"This is normal; the customer bears the restriction risk (AI-SPEC §1b)."
                    ),
                )
                await asyncio.sleep(wait_seconds)
                # Reconnect after flood wait
                try:
                    await client.connect()
                except Exception as reconnect_exc:
                    log.error("userbot.reconnect_failed", error=str(reconnect_exc))
                    raise
            except Exception as exc:
                log.error("userbot.unexpected_error", error=str(exc))
                raise

    # ── Start all loops concurrently ──────────────────────────────────────────
    log.info("userbot.starting", channels=channel_usernames)
    await asyncio.gather(
        _run_with_flood_wait_handling(),
        _heartbeat_loop(),
        _channel_reread_loop(),
    )


class _MinimalSource:
    """Minimal stand-in for the Source ORM object consumed by save_raw_items.

    save_raw_items only reads source.id; we don't need to hydrate the full ORM
    model from a raw SQL row.
    """

    def __init__(self, source_id: int) -> None:
        self.id = source_id


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_userbot())
