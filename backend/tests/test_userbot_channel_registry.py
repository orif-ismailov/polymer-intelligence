"""
Tests for userbot/channel_registry.py.

Validates that:
- load_enabled_channels returns exactly the usernames of enabled telegram_channel
  sources (adapter='telegram_channel', is_enabled=True, last_test_ok_at IS NOT NULL).
- load_enabled_channel_sources returns (source_id, username) tuples.
- Disabled sources and sources without last_test_ok_at are excluded.
- The DEC-test-before-enable invariant (last_test_ok_at IS NOT NULL) is enforced.

These are pure unit tests — no live Postgres connection required.
The SQLAlchemy session is mocked to return controlled row data.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Ensure settings are patched before importing anything that imports config
# (patch_env fixture from conftest.py handles this automatically via autouse=True).

from userbot.channel_registry import (  # noqa: E402
    load_enabled_channel_sources,
    load_enabled_channels,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_session(rows: list[tuple[object, ...]]) -> MagicMock:
    """Return a mock SQLAlchemy session whose execute().fetchall() returns rows."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_session.execute.return_value = mock_result
    return mock_session


# ── load_enabled_channels ─────────────────────────────────────────────────────


class TestLoadEnabledChannels:
    """Tests for load_enabled_channels(session) -> list[str]."""

    def test_returns_two_enabled_usernames(self) -> None:
        """With two enabled rows and one disabled row in the DB result,
        load_enabled_channels should return exactly the two enabled usernames.

        The mock simulates the SQL query result — filtering is done in SQL;
        the registry trusts that the query already applied the WHERE clause.
        We return only the rows that would match the query (enabled channels).
        """
        rows = [
            ("polymermarket_uz",),  # enabled, last_test_ok_at IS NOT NULL
            ("uzex_market",),       # enabled, last_test_ok_at IS NOT NULL
        ]
        session = _make_session(rows)

        result = load_enabled_channels(session)

        assert result == ["polymermarket_uz", "uzex_market"]
        # Verify session.execute was called once
        assert session.execute.call_count == 1

    def test_returns_empty_list_when_no_enabled_channels(self) -> None:
        """When no channels are enabled, return an empty list."""
        session = _make_session([])
        result = load_enabled_channels(session)
        assert result == []

    def test_skips_rows_with_null_username(self) -> None:
        """Rows where config->>'username' is NULL are excluded."""
        rows = [
            ("polymermarket_uz",),
            (None,),               # NULL username — should be skipped
        ]
        session = _make_session(rows)
        result = load_enabled_channels(session)
        assert result == ["polymermarket_uz"]
        assert len(result) == 1

    def test_returns_list_of_strings(self) -> None:
        """All returned values are strings (not ints or None)."""
        rows = [("channel_a",), ("channel_b",), ("channel_c",)]
        session = _make_session(rows)
        result = load_enabled_channels(session)
        assert all(isinstance(u, str) for u in result)
        assert len(result) == 3

    def test_query_contains_correct_filter_criteria(self) -> None:
        """The SQL query must filter by adapter, is_enabled, and last_test_ok_at.

        T-05-09: The enable-gate invariant (last_test_ok_at IS NOT NULL) must
        be present in the query so that channels without a passing Test are
        never subscribed to.
        """
        session = _make_session([])
        load_enabled_channels(session)

        call_args = session.execute.call_args
        # Extract the SQL text from the TextClause argument
        sql_text = str(call_args[0][0])

        assert "telegram_channel" in sql_text
        assert "is_enabled" in sql_text
        assert "last_test_ok_at" in sql_text


# ── load_enabled_channel_sources ──────────────────────────────────────────────


class TestLoadEnabledChannelSources:
    """Tests for load_enabled_channel_sources(session) -> list[tuple[int, str]]."""

    def test_returns_source_id_username_tuples(self) -> None:
        """Returns (source_id, username) tuples for enabled channels."""
        rows = [
            (1, "polymermarket_uz"),
            (3, "uzex_market"),
        ]
        session = _make_session(rows)

        result = load_enabled_channel_sources(session)

        assert result == [(1, "polymermarket_uz"), (3, "uzex_market")]

    def test_empty_result_when_no_channels(self) -> None:
        """Returns empty list when no enabled channels."""
        session = _make_session([])
        result = load_enabled_channel_sources(session)
        assert result == []

    def test_skips_rows_with_null_username(self) -> None:
        """Rows where username is NULL are excluded."""
        rows = [
            (1, "channel_ok"),
            (2, None),
        ]
        session = _make_session(rows)
        result = load_enabled_channel_sources(session)
        assert len(result) == 1
        assert result[0] == (1, "channel_ok")

    def test_source_id_is_int(self) -> None:
        """source_id must be an integer (converted from DB result)."""
        rows = [("42", "channel_a")]  # DB may return string IDs
        session = _make_session(rows)
        result = load_enabled_channel_sources(session)
        assert result == [(42, "channel_a")]
        assert isinstance(result[0][0], int)

    def test_query_contains_correct_filter_criteria(self) -> None:
        """The SQL query must enforce last_test_ok_at IS NOT NULL (T-05-09)."""
        session = _make_session([])
        load_enabled_channel_sources(session)

        call_args = session.execute.call_args
        sql_text = str(call_args[0][0])

        assert "telegram_channel" in sql_text
        assert "is_enabled" in sql_text
        assert "last_test_ok_at" in sql_text
