"""
Channel registry — reads enabled telegram_channel sources from Postgres.

Provides:
- load_enabled_channels(session) -> list[str]
      Returns the list of enabled telegram_channel usernames.
      Used to determine which channels to subscribe to.

- load_enabled_channel_sources(session) -> list[tuple[int, str]]
      Returns (source_id, username) pairs for all enabled channels.
      Used by the message handler to map an incoming message back to its
      source_id so save_raw_items can be called with the correct source.

Filter criteria (DEC-test-before-enable / T-05-09):
  adapter = 'telegram_channel'
  AND is_enabled = true
  AND last_test_ok_at IS NOT NULL

The ``last_test_ok_at IS NOT NULL`` guard enforces the Phase 4 enable-gate
invariant: a source can only be enabled if the Test button passed.
This prevents monitoring channels whose configuration has never been validated
(T-05-09 spoofing mitigation).
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def load_enabled_channels(session: Session) -> list[str]:
    """Return usernames of all enabled telegram_channel sources.

    Filters for adapter='telegram_channel' AND is_enabled=true AND
    last_test_ok_at IS NOT NULL.

    Args:
        session: Active SQLAlchemy session (read-only).

    Returns:
        Sorted list of channel usernames (without the leading @).
    """
    rows = session.execute(
        sa.text(
            """
            SELECT config->>'username' AS username
            FROM sources
            WHERE adapter = 'telegram_channel'
              AND is_enabled = true
              AND last_test_ok_at IS NOT NULL
            ORDER BY id
            """
        )
    ).fetchall()

    usernames = [str(row[0]) for row in rows if row[0]]
    logger.debug(
        "channel_registry.load_enabled_channels",
        extra={"count": len(usernames), "channels": usernames},
    )
    return usernames


def load_enabled_channel_sources(session: Session) -> list[tuple[int, str]]:
    """Return (source_id, username) pairs for all enabled telegram_channel sources.

    The message handler uses this to map an incoming Telegram message to its
    source_id so that save_raw_items can be called with the correct Source object.

    Filters for adapter='telegram_channel' AND is_enabled=true AND
    last_test_ok_at IS NOT NULL.

    Args:
        session: Active SQLAlchemy session (read-only).

    Returns:
        List of (source_id, username) tuples, sorted by source_id.
    """
    rows = session.execute(
        sa.text(
            """
            SELECT id, config->>'username' AS username
            FROM sources
            WHERE adapter = 'telegram_channel'
              AND is_enabled = true
              AND last_test_ok_at IS NOT NULL
            ORDER BY id
            """
        )
    ).fetchall()

    result = [(int(row[0]), str(row[1])) for row in rows if row[1]]
    logger.debug(
        "channel_registry.load_enabled_channel_sources",
        extra={"count": len(result)},
    )
    return result
