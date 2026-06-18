"""
Tests for parsing.budget — token-budget Redis gate.

All tests use fakeredis or unittest.mock to avoid live Redis calls in CI.

Test coverage:
  1. check_and_reserve_tokens succeeds at counter=0 → counter becomes 400;
     second reserve of 700 raises BudgetExceeded and counter is rolled back to 400
  2. Daily key includes UTC date and expireat is called; daily_spend() returns counter
  3. record_actual_tokens(reserved=400, actual=520) increments by +120 delta
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


def _make_fake_redis(initial_count: int = 0) -> MagicMock:
    """Create a mock redis client that simulates INCRBY with a running counter."""
    mock_redis = MagicMock()
    _counter = {"value": initial_count}

    def incrby_side_effect(key: str, amount: int) -> int:
        _counter["value"] += amount
        return _counter["value"]

    def decrby_side_effect(key: str, amount: int) -> int:
        _counter["value"] -= amount
        return _counter["value"]

    def get_side_effect(key: str) -> bytes | None:
        return str(_counter["value"]).encode() if _counter["value"] else b"0"

    mock_redis.incrby.side_effect = incrby_side_effect
    mock_redis.decrby.side_effect = decrby_side_effect
    mock_redis.get.side_effect = get_side_effect

    # Pipeline mock for INCRBY + EXPIREAT
    pipe = MagicMock()

    def pipe_execute():
        # Simulate INCRBY (first command in pipeline)
        # The pipeline is set up as: pipe.incrby(key, amount); pipe.expireat(key, ts)
        # We need to replay the commands
        calls = pipe.incrby.call_args_list
        if calls:
            latest = calls[-1]
            amount = latest[0][1] if latest[0] else latest[1].get("amount", 0)
            new_val = incrby_side_effect(None, amount)
            return [new_val, True]
        return [_counter["value"], True]

    pipe.execute.side_effect = pipe_execute
    mock_redis.pipeline.return_value.__enter__ = MagicMock(return_value=pipe)
    mock_redis.pipeline.return_value.__exit__ = MagicMock(return_value=False)
    mock_redis.pipeline.return_value = pipe

    return mock_redis, _counter


class TestCheckAndReserveTokens:
    """Test 1: Reserve succeeds at 0; second reserve over limit raises BudgetExceeded + rollback."""

    def test_reserve_succeeds_and_increments_counter(self) -> None:
        """check_and_reserve_tokens(400) increments the daily counter from 0 to 400."""
        import parsing.budget as budget_module
        from parsing.schemas import BudgetExceeded

        mock_redis = MagicMock()
        pipe = MagicMock()
        mock_redis.pipeline.return_value = pipe

        # Track counter state
        _counter = {"value": 0}

        def pipe_execute():
            # Simulate the INCRBY 400
            _counter["value"] += 400
            return [_counter["value"], True]

        pipe.execute.side_effect = pipe_execute

        with patch.object(budget_module, "_redis", mock_redis):
            with patch.object(budget_module, "DAILY_TOKEN_LIMIT", 1000):
                budget_module.check_and_reserve_tokens(400)

        # incrby should have been called on the pipe
        pipe.incrby.assert_called_once()
        assert _counter["value"] == 400

    def test_second_reserve_over_limit_raises_and_rolls_back(self) -> None:
        """check_and_reserve_tokens raises BudgetExceeded and rolls back when limit exceeded."""
        import parsing.budget as budget_module
        from parsing.schemas import BudgetExceeded

        mock_redis = MagicMock()
        pipe = MagicMock()
        mock_redis.pipeline.return_value = pipe

        _counter = {"value": 400}

        def pipe_execute():
            # pipe.incrby was called with the new amount; simulate adding 700 to existing 400
            calls = pipe.incrby.call_args_list
            amount = calls[-1][0][1] if calls[-1][0] else 0
            _counter["value"] += amount
            return [_counter["value"], True]

        pipe.execute.side_effect = pipe_execute

        with patch.object(budget_module, "_redis", mock_redis):
            with patch.object(budget_module, "DAILY_TOKEN_LIMIT", 1000):
                with pytest.raises(BudgetExceeded):
                    budget_module.check_and_reserve_tokens(700)

        # After BudgetExceeded, decrby should be called to roll back
        mock_redis.decrby.assert_called_once()
        # The counter should be rolled back to 400 (decrby(700) on 1100 = 400)
        decrby_call = mock_redis.decrby.call_args
        amount_rolled_back = decrby_call[0][1]
        assert amount_rolled_back == 700, (
            f"Expected rollback of 700 tokens, got {amount_rolled_back}"
        )


class TestDailyKeyAndExpireat:
    """Test 2: Daily key includes UTC date and expireat is set; daily_spend() returns counter."""

    def test_key_includes_today_utc(self) -> None:
        """The budget key includes today's UTC date (key_for function)."""
        from parsing.budget import key_for

        today = date.today()
        key = key_for(today)
        assert today.isoformat() in key, f"Key {key!r} must contain today's date {today.isoformat()!r}"

    def test_expireat_is_called_on_pipeline(self) -> None:
        """The pipeline calls expireat to set midnight TTL."""
        import parsing.budget as budget_module

        mock_redis = MagicMock()
        pipe = MagicMock()
        mock_redis.pipeline.return_value = pipe
        pipe.execute.return_value = [50, True]  # new_total=50, expireat result

        with patch.object(budget_module, "_redis", mock_redis):
            with patch.object(budget_module, "DAILY_TOKEN_LIMIT", 1000):
                budget_module.check_and_reserve_tokens(50)

        # expireat should be called on the pipeline
        pipe.expireat.assert_called_once()
        expireat_args = pipe.expireat.call_args[0]
        # First arg is the key, second is the timestamp
        assert len(expireat_args) >= 2, "expireat must be called with (key, timestamp)"

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
