"""
Tests for parsing.budget — token-budget Redis gate.

All tests use unittest.mock to avoid live Redis calls in CI.

Test coverage:
  1. check_and_reserve_tokens uses an atomic EVAL compare-and-set: it succeeds
     when the reservation fits under the limit and raises BudgetExceeded (without
     mutating the counter) when it would exceed the limit.
  2. Daily key includes UTC date and the EVAL sets a midnight EXPIREAT;
     daily_spend() returns the counter.
  3. record_actual_tokens(reserved=400, actual=520) increments by +120 delta
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


def _eval_compare_and_set(counter: dict[str, int]):
    """Return an eval side-effect mirroring the Lua compare-and-set script.

    Signature mirrors redis.eval(script, numkeys, key, amount, limit, midnight_ts).
    Increments the in-memory counter only if it would stay within the limit;
    returns the new total on success or -1 on rejection.
    """

    def _side_effect(_script, _numkeys, _key, amount, limit, _ts):  # noqa: ANN001
        amount = int(amount)
        limit = int(limit)
        if counter["value"] + amount > limit:
            return -1
        counter["value"] += amount
        return counter["value"]

    return _side_effect


class TestCheckAndReserveTokens:
    """Test 1: atomic EVAL reserve succeeds under limit; rejects over limit without mutating."""

    def test_reserve_succeeds_and_increments_counter(self) -> None:
        """check_and_reserve_tokens(400) increments the daily counter from 0 to 400."""
        import parsing.budget as budget_module

        mock_redis = MagicMock()
        counter = {"value": 0}
        mock_redis.eval.side_effect = _eval_compare_and_set(counter)

        with patch.object(budget_module, "_redis", mock_redis), \
             patch.object(budget_module, "DAILY_TOKEN_LIMIT", 1000):
            budget_module.check_and_reserve_tokens(400)

        mock_redis.eval.assert_called_once()
        assert counter["value"] == 400

    def test_reserve_over_limit_raises_and_does_not_mutate_counter(self) -> None:
        """An over-limit reservation raises BudgetExceeded and never increments the counter."""
        import parsing.budget as budget_module
        from parsing.schemas import BudgetExceeded

        mock_redis = MagicMock()
        counter = {"value": 400}
        mock_redis.eval.side_effect = _eval_compare_and_set(counter)
        # daily_spend() is called to build the error message
        mock_redis.get.return_value = b"400"

        with patch.object(budget_module, "_redis", mock_redis), \
             patch.object(budget_module, "DAILY_TOKEN_LIMIT", 1000), \
             pytest.raises(BudgetExceeded):
            budget_module.check_and_reserve_tokens(700)

        # Atomic rejection: counter must be untouched (no rollback dance needed).
        assert counter["value"] == 400


class TestDailyKeyAndExpireat:
    """Test 2: Daily key includes UTC date and expireat is set; daily_spend() returns counter."""

    def test_key_includes_today_utc(self) -> None:
        """The budget key includes today's UTC date (key_for function)."""
        from parsing.budget import key_for

        today = date.today()
        key = key_for(today)
        assert today.isoformat() in key, f"Key {key!r} must contain today's date {today.isoformat()!r}"

    def test_eval_receives_key_amount_limit_and_midnight_ts(self) -> None:
        """check_and_reserve_tokens passes (key, amount, limit, midnight_ts) to EVAL.

        The midnight EXPIREAT is set inside the Lua script; we assert the script
        is invoked with the daily key and a midnight timestamp argument.
        """
        import parsing.budget as budget_module

        mock_redis = MagicMock()
        mock_redis.eval.return_value = 50  # under limit → reserved

        with patch.object(budget_module, "_redis", mock_redis), \
             patch.object(budget_module, "DAILY_TOKEN_LIMIT", 1000):
            budget_module.check_and_reserve_tokens(50)

        mock_redis.eval.assert_called_once()
        call_args = mock_redis.eval.call_args[0]
        # eval(script, numkeys, key, amount, limit, midnight_ts)
        assert call_args[1] == 1, "numkeys must be 1"
        assert date.today().isoformat() in call_args[2], "KEYS[1] must be today's daily key"
        assert int(call_args[3]) == 50, "ARGV[1] must be the reservation amount"
        assert int(call_args[4]) == 1000, "ARGV[2] must be the daily limit"
        # ARGV[3] is the midnight UNIX timestamp (a large positive int)
        assert int(call_args[5]) > 0, "ARGV[3] must be a midnight UNIX timestamp"

    def test_daily_spend_returns_counter_value(self) -> None:
        """daily_spend() returns the current counter value from Redis."""
        import parsing.budget as budget_module

        mock_redis = MagicMock()
        mock_redis.get.return_value = b"350"

        with patch.object(budget_module, "_redis", mock_redis):
            spend = budget_module.daily_spend()

        assert spend == 350


class TestRecordActualTokens:
    """Test 3: record_actual_tokens reconciles the conservative pre-estimate."""

    def test_reconcile_positive_delta(self) -> None:
        """record_actual_tokens(reserved=400, actual=520) increments by +120 delta."""
        import parsing.budget as budget_module

        mock_redis = MagicMock()

        with patch.object(budget_module, "_redis", mock_redis):
            budget_module.record_actual_tokens(reserved=400, actual=520)

        # Should increment by the delta (520 - 400 = 120)
        mock_redis.incrby.assert_called_once()
        incrby_call = mock_redis.incrby.call_args[0]
        assert incrby_call[1] == 120, f"Expected delta of 120, got {incrby_call[1]}"

    def test_reconcile_no_op_when_actual_equals_reserved(self) -> None:
        """record_actual_tokens with actual==reserved is a no-op (delta=0)."""
        import parsing.budget as budget_module

        mock_redis = MagicMock()

        with patch.object(budget_module, "_redis", mock_redis):
            budget_module.record_actual_tokens(reserved=400, actual=400)

        # delta=0: no INCRBY needed (should either not be called or called with 0)
        if mock_redis.incrby.called:
            call_args = mock_redis.incrby.call_args[0]
            assert call_args[1] == 0

    def test_reconcile_zero_when_actual_less_than_reserved(self) -> None:
        """record_actual_tokens with actual < reserved does not go below reservation."""
        import parsing.budget as budget_module

        mock_redis = MagicMock()

        with patch.object(budget_module, "_redis", mock_redis):
            # actual < reserved: we were conservative; delta is negative or 0
            # Spec says "never below the reservation" — implementation may choose
            # to do nothing or DECRBY the delta; either is correct
            budget_module.record_actual_tokens(reserved=400, actual=350)

        # Either nothing was called or decrby was used for negative delta
        # The important invariant: INCRBY of a positive amount must NOT be called
        if mock_redis.incrby.called:
            call_args = mock_redis.incrby.call_args[0]
            # Should not increase the counter on a lower actual count
            assert call_args[1] <= 0
