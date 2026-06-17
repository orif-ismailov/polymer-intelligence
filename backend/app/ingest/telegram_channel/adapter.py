"""
TelegramChannelAdapter — pending stub for Telegram channel monitoring.

Phase-4 status (D-04/D-05): Config is saved; Test/enable are gated until
the Telethon userbot engine is built in Phase 5.

- test() always returns TestResult(ok=False, error="Available after Phase 5")
- fetch() always returns [] (no MTProto activity in Phase 4)
- is_enabled stays False because last_test_ok_at is never set

Admins can pre-stage channel configuration now; the source goes live when
Phase 5 delivers the userbot engine (D-05).

Self-registers at import time via register_adapter().
"""

from __future__ import annotations

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

    Saved at creation time; active after Phase 5 delivers the Telethon userbot.
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
        description="Number of days of history to backfill when the source is first enabled (Phase 5)",
    )


# ── Adapter ───────────────────────────────────────────────────────────────────


@dataclass
class TelegramChannelAdapter:
    """SourceAdapter stub for Telegram channels.

    Phase 4 pending: config is saved but Test and fetch are not yet functional.
    The full MTProto / Telethon implementation lands in Phase 5.
    """

    type_name: str = "telegram_channel"
    config_schema: type[BaseModel] = TelegramChannelConfig

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Return empty list — Telegram userbot engine not available until Phase 5."""
        logger.debug(
            "telegram_channel.fetch_pending",
            extra={"source_id": getattr(source, "id", None)},
        )
        return []

    async def test(self, config: dict[str, object]) -> TestResult:
        """Return ok=False — Telegram userbot engine not available until Phase 5.

        The pending stub ensures:
        - last_test_ok_at is never set -> is_enabled stays False
        - Admins see a clear message about when this will be available
        """
        return TestResult(
            ok=False,
            error="Available after Phase 5",
        )


# ── Self-register on import ────────────────────────────────────────────────────
_telegram_channel_adapter = TelegramChannelAdapter()
register_adapter(_telegram_channel_adapter)
