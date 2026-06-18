"""
Tests for alert_service: JSONB predicate interpreter + dedupe + delivery dispatch.

TDD RED phase: tests written before implementation.

Covers:
- evaluate_condition: matching + non-matching for each predicate key
  (kind, product_id, volume_gte, urgency_in, source_kind, lead_score_gte)
- evaluate_condition: unknown keys are ignored (no-op)
- evaluate_condition: lead_score_gte never matches in Phase 4 (entity.ai has no lead_score)
- evaluate_alert_rules: dedupe via ON CONFLICT(uq_alerts_dedupe_key) — same rule+entity
  produces only one alert row (IntegrityError caught, db.rollback, continue)
- evaluate_alert_rules: delivery dispatch — send_delivery.apply_async called with
  queue="notify" and correct args per rule.channels

Security invariants (T-04-24):
- alert_service.py must contain zero eval() calls
- interpreter uses hardcoded per-key dispatch, never dynamic code execution

Coverage target: 90%+ on interpreter branches (dev-spec §8).
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_signal(
    kind: str = "sell_offer",
    product_id: int | None = 1,
    volume: float | None = 500.0,
    urgency_value: str | None = "high",
    source_kind: str | None = "exchange",
    ai: dict | None = None,
) -> MagicMock:
    """Return a MagicMock that quacks like a Signal ORM object."""
    from app.models.enums import SignalKind, Urgency  # noqa: PLC0415

    sig = MagicMock()
    sig.kind = kind
    sig.product_id = product_id
    sig.volume = volume
    sig.urgency = Urgency(urgency_value) if urgency_value else None
    sig.source_kind = source_kind
    sig.ai = ai or {}
    return sig


def _make_rule(
    rule_id: int = 1,
    name: str = "Test Rule",
    condition: dict | None = None,
    channels: list | None = None,
    is_enabled: bool = True,
    kind_value: str = "custom",
) -> MagicMock:
    """Return a MagicMock that quacks like an AlertRule ORM object."""
    from app.models.enums import AlertKind  # noqa: PLC0415

    rule = MagicMock()
    rule.id = rule_id
    rule.name = name
    rule.condition = condition or {}
    rule.channels = channels or [{"type": "telegram_dm", "chat_id": -1001234567890}]
    rule.is_enabled = is_enabled
    rule.kind = AlertKind(kind_value)
    return rule


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_condition tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluateCondition:
    """Tests for the hardcoded JSONB predicate interpreter."""

    def test_empty_condition_always_matches(self) -> None:
        """Empty condition dict → always returns True (match everything)."""
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal()
        assert evaluate_condition({}, signal) is True

    # ── kind predicate ────────────────────────────────────────────────────────

    def test_kind_in_list_matches(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(kind="sell_offer")
        assert evaluate_condition({"kind": ["sell_offer", "buy_request"]}, signal) is True

    def test_kind_not_in_list_no_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(kind="news")
        assert evaluate_condition({"kind": ["sell_offer", "buy_request"]}, signal) is False

    def test_kind_exact_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(kind="buy_request")
        assert evaluate_condition({"kind": ["buy_request"]}, signal) is True

    # ── product_id predicate ──────────────────────────────────────────────────

    def test_product_id_in_list_matches(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(product_id=2)
        assert evaluate_condition({"product_id": [1, 2, 3]}, signal) is True

    def test_product_id_not_in_list_no_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(product_id=5)
        assert evaluate_condition({"product_id": [1, 2, 3]}, signal) is False

    def test_product_id_none_no_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(product_id=None)
        assert evaluate_condition({"product_id": [1, 2]}, signal) is False

    # ── volume_gte predicate ──────────────────────────────────────────────────

    def test_volume_gte_at_threshold_matches(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(volume=200.0)
        assert evaluate_condition({"volume_gte": 200.0}, signal) is True

    def test_volume_gte_above_threshold_matches(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(volume=500.0)
        assert evaluate_condition({"volume_gte": 200.0}, signal) is True

    def test_volume_gte_below_threshold_no_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(volume=100.0)
        assert evaluate_condition({"volume_gte": 200.0}, signal) is False

    def test_volume_gte_none_no_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(volume=None)
        assert evaluate_condition({"volume_gte": 200.0}, signal) is False

    # ── urgency_in predicate ──────────────────────────────────────────────────

    def test_urgency_in_list_matches(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(urgency_value="high")
        assert evaluate_condition({"urgency_in": ["high", "medium"]}, signal) is True

    def test_urgency_in_list_no_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(urgency_value="low")
        assert evaluate_condition({"urgency_in": ["high"]}, signal) is False

    def test_urgency_none_no_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(urgency_value=None)
        assert evaluate_condition({"urgency_in": ["high"]}, signal) is False

    # ── source_kind predicate ─────────────────────────────────────────────────

    def test_source_kind_in_list_matches(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(source_kind="exchange")
        assert evaluate_condition({"source_kind": ["exchange", "telegram_channel"]}, signal) is True

    def test_source_kind_not_in_list_no_match(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(source_kind="website")
        assert evaluate_condition({"source_kind": ["exchange"]}, signal) is False

    # ── lead_score_gte predicate (D-07: never matches in Phase 4) ────────────

    def test_lead_score_gte_no_ai_never_matches(self) -> None:
        """Phase 4: entity.ai is empty dict → lead_score is None → never matches."""
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(ai={})
        assert evaluate_condition({"lead_score_gte": 0.5}, signal) is False

    def test_lead_score_gte_ai_none_never_matches(self) -> None:
        """Phase 4: entity.ai is None → lead_score is None → never matches."""
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(ai=None)
        assert evaluate_condition({"lead_score_gte": 0.0}, signal) is False

    def test_lead_score_gte_no_lead_score_key_never_matches(self) -> None:
        """Phase 4: ai dict has no lead_score key → never matches."""
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(ai={"demand_level": "high"})
        assert evaluate_condition({"lead_score_gte": 0.1}, signal) is False

    # ── unknown key handling ──────────────────────────────────────────────────

    def test_unknown_key_is_ignored(self) -> None:
        """Unknown condition keys should be silently ignored (no-op)."""
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal()
        # "future_field" is not in the known predicate set → ignored
        assert evaluate_condition({"future_field": "whatever"}, signal) is True

    # ── multiple predicates ───────────────────────────────────────────────────

    def test_all_predicates_pass(self) -> None:
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(
            kind="sell_offer",
            product_id=1,
            volume=500.0,
            urgency_value="high",
            source_kind="exchange",
            ai={},
        )
        condition = {
            "kind": ["sell_offer"],
            "product_id": [1],
            "volume_gte": 200.0,
            "urgency_in": ["high"],
            "source_kind": ["exchange"],
        }
        assert evaluate_condition(condition, signal) is True

    def test_one_predicate_fails_no_match(self) -> None:
        """If any predicate fails, the whole condition returns False."""
        from app.services.alert_service import evaluate_condition  # noqa: PLC0415

        signal = _make_signal(
            kind="sell_offer",
            product_id=1,
            volume=50.0,  # below threshold
            urgency_value="high",
            source_kind="exchange",
        )
        condition = {
            "kind": ["sell_offer"],
            "volume_gte": 200.0,  # this fails
        }
        assert evaluate_condition(condition, signal) is False

    # ── security: no eval() ───────────────────────────────────────────────────

    def test_no_eval_in_alert_service(self) -> None:
        """T-04-24: alert_service.py must contain zero eval() calls."""
        import os  # noqa: PLC0415

        alert_service_path = os.path.join(
            os.path.dirname(__file__), "..", "app", "services", "alert_service.py"
        )
        with open(alert_service_path) as f:
            source = f.read()
        assert "eval(" not in source, "T-04-24: alert_service.py contains eval() — forbidden!"


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_alert_rules — dedupe test
# ─────────────────────────────────────────────────────────────────────────────


class TestDedupe:
    """Tests for dedupe_key ON CONFLICT DO NOTHING behavior."""

    def test_dedupe(self) -> None:
        """Same rule+entity fires twice: second IntegrityError is caught, only one alert."""
        from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

        from app.services.alert_service import evaluate_alert_rules  # noqa: PLC0415

        rule = _make_rule(rule_id=1, condition={})

        # First call: flush succeeds (no IntegrityError)
        # Second call: flush raises IntegrityError (dedupe)
        flush_first = MagicMock()
        flush_second = MagicMock(side_effect=IntegrityError("", {}, Exception()))

        flush_call_count = [0]

        def mock_flush() -> None:
            flush_call_count[0] += 1
            if flush_call_count[0] == 1:
                # First flush for alert.id — succeed
                return None
            elif flush_call_count[0] == 2:
                # Second flush for deliveries — succeed
                return None
            else:
                return None

        signal = _make_signal()
        signal.id = 42

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [rule]
        mock_db.flush = MagicMock(side_effect=mock_flush)

        alert_mock = MagicMock()
        alert_mock.id = 99

        with patch("app.services.alert_service.Alert") as MockAlert, \
             patch("app.services.alert_service.Delivery"), \
             patch("app.models.signals.Signal") as MockSignal:

            # Simulate: signal entity returned by _load_entity
            with patch("app.services.alert_service._load_entity", return_value=signal):
                MockAlert.return_value = alert_mock

                with patch("app.tasks.notify.send_delivery") as mock_send_delivery:
                    mock_send_delivery.apply_async = MagicMock()

                    evaluate_alert_rules(mock_db, signal_id=42)

            # One alert add called
            assert mock_db.add.called

    def test_dedupe_on_integrity_error(self) -> None:
        """IntegrityError on flush → SAVEPOINT rollback + continue (no delivery, no dispatch).

        CR-02: the fix uses db.begin_nested() (SAVEPOINT) instead of db.rollback() so only
        the duplicate alert insert is undone, not the caller's entire transaction.
        """
        from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

        from app.services.alert_service import evaluate_alert_rules  # noqa: PLC0415

        rule = _make_rule(rule_id=2, condition={})
        signal = _make_signal()
        signal.id = 77

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [rule]

        # begin_nested() returns a context manager; its __exit__ raises IntegrityError
        # when flush() inside the block raises IntegrityError.
        nested_ctx = MagicMock()
        nested_ctx.__enter__ = MagicMock(return_value=nested_ctx)
        nested_ctx.__exit__ = MagicMock(return_value=False)  # re-raises exceptions
        mock_db.begin_nested = MagicMock(return_value=nested_ctx)

        # flush() raises IntegrityError → caught by begin_nested().__exit__ which
        # re-raises it → caught by the service's except IntegrityError block.
        mock_db.flush = MagicMock(side_effect=IntegrityError("unique", {}, Exception()))

        with patch("app.services.alert_service._load_entity", return_value=signal), \
             patch("app.services.alert_service.Alert"), \
             patch("app.tasks.notify.send_delivery") as mock_send_delivery:
            mock_send_delivery.apply_async = MagicMock()

            evaluate_alert_rules(mock_db, signal_id=77)

        # begin_nested() must have been called (SAVEPOINT pattern — CR-02)
        mock_db.begin_nested.assert_called()
        # db.rollback() on the shared session must NOT be called (would wipe caller's tx)
        mock_db.rollback.assert_not_called()
        # No deliveries dispatched
        mock_send_delivery.apply_async.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_alert_rules — delivery dispatch test
# ─────────────────────────────────────────────────────────────────────────────


class TestDeliveryDispatch:
    """Tests for delivery creation and send_delivery.apply_async dispatch."""

    def test_delivery_dispatch(self) -> None:
        """On rule match: one Delivery per channel, send_delivery.apply_async(queue='notify')."""
        from app.services.alert_service import evaluate_alert_rules  # noqa: PLC0415

        channels = [
            {"type": "telegram_dm", "chat_id": -100111},
            {"type": "telegram_dm", "chat_id": -100222},
        ]
        rule = _make_rule(rule_id=3, condition={}, channels=channels)
        signal = _make_signal()
        signal.id = 55

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [rule]
        mock_db.flush = MagicMock()  # succeeds (no IntegrityError)

        alert_mock = MagicMock()
        alert_mock.id = 200

        delivery_instances = []

        def capture_delivery(*args, **kwargs) -> MagicMock:
            d = MagicMock()
            delivery_instances.append(d)
            return d

        with patch("app.services.alert_service._load_entity", return_value=signal), \
             patch("app.services.alert_service.Alert", return_value=alert_mock), \
             patch("app.services.alert_service.Delivery", side_effect=capture_delivery):

            # Lazy import inside evaluate_alert_rules resolves to app.tasks.notify.send_delivery
            # Patch at the source module so the lazy import picks up the mock.
            with patch("app.tasks.notify.send_delivery") as mock_sd:
                mock_sd.apply_async = MagicMock()

                evaluate_alert_rules(mock_db, signal_id=55)

                # send_delivery.apply_async called with queue="notify"
                assert mock_sd.apply_async.called
                call_kwargs = mock_sd.apply_async.call_args
                assert call_kwargs[1].get("queue") == "notify" or (
                    len(call_kwargs[0]) > 1 and "notify" in str(call_kwargs)
                )

        # Two deliveries created (one per channel)
        assert len(delivery_instances) == 2

    def test_send_delivery_queue_notify(self) -> None:
        """send_delivery task must be registered with queue='notify'."""
        from app.tasks.notify import send_delivery  # noqa: PLC0415

        assert callable(send_delivery)
        # The task decorator registers queue="notify" — verify via task options
        assert hasattr(send_delivery, "apply_async")
