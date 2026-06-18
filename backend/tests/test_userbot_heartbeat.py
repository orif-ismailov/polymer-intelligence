"""
Tests for userbot/heartbeat.py.

Validates that:
- write_heartbeat sets the HEARTBEAT_KEY in Redis with a TTL.
- read_heartbeat round-trips a float timestamp.
- read_heartbeat returns None when the key is absent.
- The heartbeat key is HEARTBEAT_KEY = "userbot:heartbeat".

These are pure unit tests — no live Redis connection required.
Redis is mocked with a simple in-memory MagicMock/dict.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

# patch_env autouse fixture from conftest.py handles Settings env patching.

from userbot.heartbeat import HEARTBEAT_KEY, read_heartbeat, write_heartbeat


# ── Simple in-memory Redis mock ───────────────────────────────────────────────


class _InMemoryRedis:
    """Minimal Redis mock that stores key-value pairs in a dict.

    Supports set(key, value, ex=...) and get(key) — the only methods
    used by write_heartbeat and read_heartbeat.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    def get(self, key: str) -> str | None:
        return self._store.get(key)


# ── HEARTBEAT_KEY constant ────────────────────────────────────────────────────


def test_heartbeat_key_constant() -> None:
    """HEARTBEAT_KEY is the agreed Redis key name for the userbot liveness signal."""
    assert HEARTBEAT_KEY == "userbot:heartbeat"


# ── write_heartbeat ───────────────────────────────────────────────────────────


class TestWriteHeartbeat:
    """Tests for write_heartbeat(redis)."""

    def test_sets_heartbeat_key(self) -> None:
        """write_heartbeat sets HEARTBEAT_KEY in Redis."""
        redis = _InMemoryRedis()
        write_heartbeat(redis)
        assert redis.get(HEARTBEAT_KEY) is not None

    def test_heartbeat_value_is_float_string(self) -> None:
        """The stored value is a string representation of a float (Unix timestamp)."""
        redis = _InMemoryRedis()
        before = time.time()
        write_heartbeat(redis)
        after = time.time()

        raw = redis.get(HEARTBEAT_KEY)
        assert raw is not None
        ts = float(raw)
        assert before <= ts <= after

    def test_sets_ttl(self) -> None:
        """write_heartbeat calls redis.set with an ex= TTL argument."""
        mock_redis = MagicMock()
        write_heartbeat(mock_redis)

        # Verify redis.set was called with ex= keyword argument
        assert mock_redis.set.called
        call_kwargs = mock_redis.set.call_args
        # ex should be present in kwargs (USERBOT_HEARTBEAT_SECONDS * 10)
        assert "ex" in call_kwargs.kwargs or (
            len(call_kwargs.args) >= 3  # positional: key, value, ex
        ), "write_heartbeat must pass a TTL (ex=) to redis.set"

    def test_ttl_is_positive(self) -> None:
        """The TTL passed to redis.set must be a positive integer."""
        mock_redis = MagicMock()
        write_heartbeat(mock_redis)

        call_kwargs = mock_redis.set.call_args
        ex_val = call_kwargs.kwargs.get("ex")
        if ex_val is None and len(call_kwargs.args) >= 3:
            ex_val = call_kwargs.args[2]
        assert isinstance(ex_val, int)
        assert ex_val > 0


# ── read_heartbeat ────────────────────────────────────────────────────────────


class TestReadHeartbeat:
    """Tests for read_heartbeat(redis) -> float | None."""

    def test_returns_none_when_key_absent(self) -> None:
        """read_heartbeat returns None when HEARTBEAT_KEY is not set."""
        redis = _InMemoryRedis()
        result = read_heartbeat(redis)
        assert result is None

    def test_roundtrips_float(self) -> None:
        """write_heartbeat then read_heartbeat returns a valid float timestamp."""
        redis = _InMemoryRedis()
        before = time.time()
        write_heartbeat(redis)
        result = read_heartbeat(redis)
        after = time.time()

        assert result is not None
        assert isinstance(result, float)
        assert before <= result <= after

    def test_returns_none_for_missing_mock_key(self) -> None:
        """read_heartbeat with a MagicMock redis that returns None returns None."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        result = read_heartbeat(mock_redis)
        assert result is None
        mock_redis.get.assert_called_once_with(HEARTBEAT_KEY)

    def test_returns_float_from_stored_value(self) -> None:
        """read_heartbeat converts a stored string to float correctly."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"1718700000.123456"  # bytes (redis-py returns bytes)
        result = read_heartbeat(mock_redis)
        assert result is not None
        assert abs(result - 1718700000.123456) < 0.001

    def test_returns_none_on_invalid_stored_value(self) -> None:
        """read_heartbeat returns None if the stored value is not a valid float."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"not_a_float"
        result = read_heartbeat(mock_redis)
        assert result is None

    def test_reads_from_correct_key(self) -> None:
        """read_heartbeat calls redis.get with HEARTBEAT_KEY."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        read_heartbeat(mock_redis)
        mock_redis.get.assert_called_once_with(HEARTBEAT_KEY)
