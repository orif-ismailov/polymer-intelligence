"""
TelegramChannelAdapter — live Telegram channel monitoring adapter.

Phase-5 implementation (replaces the Phase-4 pending stub):
- test(config): validate config, resolve the channel by username via Telethon,
  fetch up to 10 recent messages, return TestResult(ok=True, sample_rows=[...]).
  On any telethon error, return TestResult(ok=False, error=...) so the enable-gate
  keeps the source disabled (DEC-test-before-enable / T-05-09).
- fetch(source): pull up to config.backfill_days of recent history as RawItemDraft list.
  Live ingestion is the userbot's job; fetch() is the wizard/backfill path.

Telethon is imported lazily inside test()/fetch() to keep module import-time
socket-free (mirroring DEC-http-client-deferred-import pattern from http_client.py).

Self-registers at import time via register_adapter().
"""

from __future__ import annotations

import contextlib
import datetime
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.ingest.base import RawItemDraft, TestResult
from app.ingest.registry import register_adapter

if TYPE_CHECKING:
    from app.models.sources import Source

logger = logging.getLogger(__name__)


# ── Config schema ─────────────────────────────────────────────────────────────


class TelegramChannelConfig(BaseModel):
    """Configuration for the telegram_channel adapter.

    Saved at creation time; live after Phase 5 delivers the Telethon userbot.
    """

    username: str = Field(
        ...,
        description="Public Telegram channel username (without @), e.g. 'polymermarket_uz'",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Optional keyword filters — only messages containing these words are ingested",
    )
    backfill_days: int = Field(
        default=7,
        description="Number of days of history to backfill when the source is first enabled",
    )


# ── Adapter ───────────────────────────────────────────────────────────────────


@dataclass
class TelegramChannelAdapter:
    """Live SourceAdapter for Telegram channels (Phase 5).

    test() validates channel reachability and returns ≤10 sample rows.
    fetch() backfills history via Telethon (wizard/backfill path only;
    live ingestion is handled by the userbot process).
    """

    type_name: str = "telegram_channel"
    config_schema: type[BaseModel] = TelegramChannelConfig

    async def test(self, config: dict[str, object]) -> TestResult:
        """Test channel reachability and return up to 10 sample rows.

        Validates the config dict against TelegramChannelConfig, builds a
        short-lived Telethon client (lazy import — socket-free at import time),
        resolves the channel by username, and fetches ≤10 recent messages.

        Returns:
            TestResult(ok=True, sample_rows=[{external_id, text_excerpt, date}...])
            on success, capped at 10 rows.
            TestResult(ok=False, error=<message>) on any telethon error (channel
            not found, not authorized, FloodWait, session string absent, etc.) so
            the enable-gate keeps the source disabled (T-05-09).

        Security:
            T-05-09: ok=False on any error ensures last_test_ok_at is never set for
            unreachable/misconfigured channels, preventing the userbot from subscribing
            to them.
        """
        # ── Lazy import of telethon (socket-free at module import time) ───────
        try:
            from telethon import TelegramClient  # noqa: PLC0415
            from telethon.errors import FloodWaitError  # noqa: PLC0415
            from telethon.sessions import StringSession  # noqa: PLC0415
        except ImportError as exc:
            return TestResult(ok=False, error=f"telethon not available: {exc}")

        # ── Validate config ───────────────────────────────────────────────────
        try:
            channel_config = TelegramChannelConfig.model_validate(config)
        except Exception as exc:
            return TestResult(ok=False, error=f"Invalid config: {exc}")

        # ── Build session string from settings ────────────────────────────────
        try:
            from app.core.config import settings  # noqa: PLC0415
        except Exception as exc:
            return TestResult(ok=False, error=f"Config unavailable: {exc}")

        if not settings.TG_SESSION_STRING:
            return TestResult(
                ok=False,
                error=(
                    "TG_SESSION_STRING is not set. "
                    "Generate a session string via the procedure in userbot/session.py "
                    "and add it to .env."
                ),
            )

        # ── Connect and resolve channel ────────────────────────────────────────
        client = TelegramClient(
            StringSession(settings.TG_SESSION_STRING),
            int(settings.TG_API_ID),
            settings.TG_API_HASH,
        )

        try:
            await client.connect()

            if not await client.is_user_authorized():
                return TestResult(
                    ok=False,
                    error="Telegram session is not authorized. Regenerate TG_SESSION_STRING.",
                )

            # Resolve the entity — raises ValueError/ChannelInvalidError if not found
            entity = await client.get_entity(channel_config.username)

            # Fetch up to 10 recent messages
            sample_rows: list[dict[str, object]] = []
            async for message in client.iter_messages(entity, limit=10):
                text: str = message.message or ""
                if text.strip():
                    sample_rows.append(
                        {
                            "external_id": str(message.id),
                            "text_excerpt": text[:200],  # cap excerpt at 200 chars
                            "date": message.date.isoformat() if message.date else None,
                        }
                    )

            return TestResult(ok=True, sample_rows=sample_rows)  # TestResult caps at 10

        except FloodWaitError as exc:
            wait = exc.seconds
            logger.warning(
                "telegram_channel_adapter.test_flood_wait",
                extra={"username": channel_config.username, "wait_seconds": wait},
            )
            return TestResult(
                ok=False,
                error=f"Telegram rate-limited the test (FloodWait {wait}s). Try again later.",
            )
        except Exception as exc:
            logger.warning(
                "telegram_channel_adapter.test_error",
                extra={"username": channel_config.username, "error": str(exc)},
            )
            return TestResult(ok=False, error=str(exc))
        finally:
            with contextlib.suppress(Exception):
                await client.disconnect()

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Backfill recent history for the source (wizard/backfill path).

        Pulls up to ``config.backfill_days`` of messages from the channel and
        returns them as RawItemDraft objects. The caller (ingest task) is
        responsible for calling save_raw_items with the returned drafts.

        Live real-time ingestion is handled by the userbot process (not this method).

        Args:
            source: Source ORM object with .config containing TelegramChannelConfig fields.

        Returns:
            List of RawItemDraft objects (may be empty if no messages or session absent).
        """
        # ── Lazy import ───────────────────────────────────────────────────────
        try:
            from telethon import TelegramClient  # noqa: PLC0415
            from telethon.errors import FloodWaitError  # noqa: PLC0415
            from telethon.sessions import StringSession  # noqa: PLC0415
        except ImportError:
            logger.error("telegram_channel_adapter.fetch_telethon_unavailable")
            return []

        # ── Parse source config ───────────────────────────────────────────────
        try:
            from app.core.config import settings  # noqa: PLC0415

            raw_config: dict[str, object] = source.config if isinstance(source.config, dict) else {}
            channel_config = TelegramChannelConfig.model_validate(raw_config)
        except Exception as exc:
            logger.error(
                "telegram_channel_adapter.fetch_config_error",
                extra={"source_id": getattr(source, "id", None), "error": str(exc)},
            )
            return []

        if not settings.TG_SESSION_STRING:
            logger.warning(
                "telegram_channel_adapter.fetch_no_session",
                extra={"source_id": getattr(source, "id", None)},
            )
            return []

        # ── Connect and pull history ──────────────────────────────────────────
        client = TelegramClient(
            StringSession(settings.TG_SESSION_STRING),
            int(settings.TG_API_ID),
            settings.TG_API_HASH,
        )

        drafts: list[RawItemDraft] = []
        cutoff = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(
            days=channel_config.backfill_days
        )

        try:
            await client.connect()

            if not await client.is_user_authorized():
                logger.warning(
                    "telegram_channel_adapter.fetch_not_authorized",
                    extra={"source_id": getattr(source, "id", None)},
                )
                return []

            entity = await client.get_entity(channel_config.username)

            async for message in client.iter_messages(entity, offset_date=cutoff, reverse=True):
                # Skip empty/media-only messages (G6 cost guard)
                text = message.message or ""
                if not text.strip():
                    continue

                # Filter by keywords if configured
                if channel_config.keywords:
                    text_lower = text.lower()
                    if not any(kw.lower() in text_lower for kw in channel_config.keywords):
                        continue

                # fwd_from metadata for stale-repost detection (AI-SPEC §4b.4)
                fwd_from = message.fwd_from
                is_forwarded = fwd_from is not None
                fwd_from_date: str | None = None
                if fwd_from is not None and hasattr(fwd_from, "date") and fwd_from.date:
                    fwd_from_date = fwd_from.date.isoformat()

                payload: dict[str, object] = {
                    "is_forwarded": is_forwarded,
                    "fwd_from_date": fwd_from_date,
                    "username": channel_config.username,
                }

                drafts.append(
                    RawItemDraft(
                        external_id=str(message.id),
                        content=text.strip(),
                        payload=payload,
                        event_at=message.date,
                    )
                )

        except FloodWaitError as exc:
            logger.warning(
                "telegram_channel_adapter.fetch_flood_wait",
                extra={
                    "source_id": getattr(source, "id", None),
                    "wait_seconds": exc.seconds,
                },
            )
        except Exception as exc:
            logger.error(
                "telegram_channel_adapter.fetch_error",
                extra={"source_id": getattr(source, "id", None), "error": str(exc)},
            )
        finally:
            with contextlib.suppress(Exception):
                await client.disconnect()

        logger.info(
            "telegram_channel_adapter.fetch_done",
            extra={
                "source_id": getattr(source, "id", None),
                "channel": channel_config.username,
                "drafts": len(drafts),
                "backfill_days": channel_config.backfill_days,
            },
        )
        return drafts


# ── Self-register on import ────────────────────────────────────────────────────
_telegram_channel_adapter = TelegramChannelAdapter()
register_adapter(_telegram_channel_adapter)
