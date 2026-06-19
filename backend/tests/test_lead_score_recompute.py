"""
Tests for lead_score_recompute_service.rescore_on_prompt_version_change.

Covers:
- Stale signals are re-scored and signals.ai is overwritten with new version.
- Signals already at the new version are NOT re-scored (skipped).
- Returned count matches the number of actually re-scored signals.
- The service never commits (caller commits) — verifiable via mock session.
- Re-scored ai JSONB contains new scoring_prompt_version + scored_at.

All tests use a mock SQLAlchemy session (no live DB required).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

# app.* imports are deferred inside test methods (PLC0415 pattern) to avoid
# importing app.core.config at module collection time before conftest
# patch_env fixture has set the required environment variables.


# ---------------------------------------------------------------------------
# Helpers to build mock Signal objects
# ---------------------------------------------------------------------------


def _make_signal(
    signal_id: int,
    *,
    kind_value: str = "sell_offer",
    volume: Decimal | None = Decimal("50"),
    price: Decimal | None = Decimal("950"),
    currency: str | None = "USD",
    counterparty_text: str | None = None,
    urgency_value: str | None = None,
    scoring_prompt_version: str = "lead_v0",
    lead_score: float = 0.5,
    classification: str = "MEDIUM",
) -> MagicMock:
    """Build a mock Signal ORM object with ai JSONB populated."""
    signal = MagicMock()
    signal.id = signal_id

    # kind as enum-like object
    kind_mock = MagicMock()
    kind_mock.value = kind_value
    signal.kind = kind_mock

    signal.volume = volume
    signal.volume_unit = "MT"
    signal.price = price
    signal.currency = currency
    signal.counterparty_text = counterparty_text
    signal.region = None
    signal.grade_text = None

    # urgency as enum-like or None
    if urgency_value is not None:
        urgency_mock = MagicMock()
        urgency_mock.value = urgency_value
        signal.urgency = urgency_mock
    else:
        signal.urgency = None

    # ai JSONB with stale scoring_prompt_version
    signal.ai = {
        "lead_score": lead_score,
        "classification": classification,
        "scoring_prompt_version": scoring_prompt_version,
        "scored_at": "2026-01-01T00:00:00+00:00",
        "model": "claude-haiku-4-5",
        "prompt_version": "v1",
        "needs_review": False,
        "confidence": 0.85,
    }

    return signal


def _make_mock_session(stale_signals: list[Any]) -> MagicMock:
    """Build a mock session whose query returns stale_signals on the first batch, then [].

    The service now uses keyset pagination, so the chain is:
    session.query(...).filter(...).filter(...).filter(...).order_by(...).limit(...).all()
    (no .offset()). The mock returns the full stale_signals list on the first
    .all() and an empty list thereafter, mirroring "all stale rows consumed in
    one batch, next keyset page is empty".
    """
    session = MagicMock()
    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.order_by.return_value = query_mock

    call_count = [0]

    def _limit(limit_val: int) -> MagicMock:
        all_mock = MagicMock()

        def _all() -> list[Any]:
            call_count[0] += 1
            if call_count[0] == 1:
                return stale_signals
            return []

        all_mock.all = _all
        return all_mock

    query_mock.limit = _limit
    session.query.return_value = query_mock
    return session


def _make_keyset_mock_session(
    all_signals: list[Any], *, new_version: str, batch_size: int
) -> MagicMock:
    """Build a mock session that emulates real keyset pagination semantics.

    Each .all() returns the next batch_size signals that are (a) still stale
    (scoring_prompt_version != new_version) and (b) have id greater than the
    highest id already handed out — exactly the WHERE Signal.id > last_id keyset
    the service applies. Because the service mutates signal.ai in place, rescored
    rows drop out of the "stale" set on subsequent batches. This catches the
    OFFSET-skip bug: an OFFSET-based loop would skip not-yet-processed rows.
    """
    session = MagicMock()
    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.order_by.return_value = query_mock

    cursor = {"last_id": 0}
    ordered = sorted(all_signals, key=lambda s: s.id)

    def _limit(limit_val: int) -> MagicMock:
        all_mock = MagicMock()

        def _all() -> list[Any]:
            batch = [
                s
                for s in ordered
                if s.id > cursor["last_id"]
                and s.ai.get("scoring_prompt_version") != new_version
            ][:limit_val]
            if batch:
                cursor["last_id"] = batch[-1].id
            return batch

        all_mock.all = _all
        return all_mock

    query_mock.limit = _limit
    session.query.return_value = query_mock
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRescoreOnPromptVersionChange:
    """Tests for rescore_on_prompt_version_change."""

    def test_stale_signals_are_rescored(self) -> None:
        """Stale signals get new scoring_prompt_version stamped on their ai JSONB."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        old_version = "lead_v0"
        new_version = "lead_v2"
        signals = [
            _make_signal(1, scoring_prompt_version=old_version),
            _make_signal(2, scoring_prompt_version=old_version, volume=Decimal("200")),
        ]
        session = _make_mock_session(signals)

        count = rescore_on_prompt_version_change(session, new_version=new_version)

        assert count == 2
        for signal in signals:
            assert signal.ai["scoring_prompt_version"] == new_version
            assert "scored_at" in signal.ai
            assert "lead_score" in signal.ai
            assert "classification" in signal.ai

    def test_rescored_ai_overwritten_in_place(self) -> None:
        """signals.ai is overwritten with new version + preserves model/prompt_version."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        old_version = "lead_v0"
        new_version = "lead_v1"
        signal = _make_signal(1, scoring_prompt_version=old_version)
        original_model = signal.ai["model"]
        original_prompt_version = signal.ai["prompt_version"]
        session = _make_mock_session([signal])

        rescore_on_prompt_version_change(session, new_version=new_version)

        # Immutable attribution fields are preserved
        assert signal.ai["model"] == original_model
        assert signal.ai["prompt_version"] == original_prompt_version
        # Mutable scoring fields are overwritten
        assert signal.ai["scoring_prompt_version"] == new_version

    def test_returned_count_matches_rescored(self) -> None:
        """Returned count exactly matches the number of re-scored signals."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        signals = [_make_signal(i, scoring_prompt_version="lead_v0") for i in range(1, 6)]
        session = _make_mock_session(signals)

        count = rescore_on_prompt_version_change(session, new_version=new_version)

        assert count == len(signals)

    def test_empty_ai_signals_are_skipped(self) -> None:
        """Signals with empty ai JSONB are skipped (no extraction yet)."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        signal_empty_ai = _make_signal(1, scoring_prompt_version="lead_v0")
        signal_empty_ai.ai = {}  # empty ai — no extraction yet
        signal_normal = _make_signal(2, scoring_prompt_version="lead_v0")
        session = _make_mock_session([signal_empty_ai, signal_normal])

        count = rescore_on_prompt_version_change(session, new_version=new_version)

        # Only the normal signal is re-scored
        assert count == 1
        # Empty ai signal is untouched
        assert signal_empty_ai.ai == {}

    def test_multi_batch_keyset_rescores_all_rows(self) -> None:
        """WR-04: a stale set larger than one batch — every row reaches new_version.

        Uses a keyset-aware mock that filters on Signal.id > last_id (the same
        predicate the service applies) so the OFFSET-skip bug would be caught:
        an advancing OFFSET would skip whole batches of not-yet-processed rows.
        """
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        batch_size = 2
        signals = [_make_signal(i, scoring_prompt_version="lead_v0") for i in range(1, 6)]

        session = _make_keyset_mock_session(signals, new_version=new_version, batch_size=batch_size)

        count = rescore_on_prompt_version_change(
            session, new_version=new_version, batch_size=batch_size
        )

        assert count == len(signals)
        for signal in signals:
            assert signal.ai["scoring_prompt_version"] == new_version

    def test_session_flush_called(self) -> None:
        """session.flush() is called after each batch (service-never-commits)."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        signals = [_make_signal(1, scoring_prompt_version="lead_v0")]
        session = _make_mock_session(signals)

        rescore_on_prompt_version_change(session, new_version=new_version)

        session.flush.assert_called()

    def test_session_commit_never_called(self) -> None:
        """session.commit() is NEVER called (service-never-commits axiom)."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        signals = [_make_signal(1, scoring_prompt_version="lead_v0")]
        session = _make_mock_session(signals)

        rescore_on_prompt_version_change(session, new_version=new_version)

        session.commit.assert_not_called()

    def test_scored_at_is_fresh_iso_timestamp(self) -> None:
        """Re-scored signal has a fresh scored_at ISO-8601 timestamp."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        signal = _make_signal(1, scoring_prompt_version="lead_v0")
        session = _make_mock_session([signal])

        rescore_on_prompt_version_change(session, new_version=new_version)

        new_scored_at = signal.ai["scored_at"]
        parsed = datetime.datetime.fromisoformat(new_scored_at)
        assert parsed.tzinfo is not None, "scored_at must be timezone-aware"

    def test_large_volume_signal_gets_hot_classification(self) -> None:
        """A signal with >100 MT volume + deal kind gets HOT classification."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        signal = _make_signal(
            1,
            kind_value="deal",
            volume=Decimal("150"),
            counterparty_text="TestCorp",
            scoring_prompt_version="lead_v0",
        )
        session = _make_mock_session([signal])

        rescore_on_prompt_version_change(session, new_version=new_version)

        # deal (0.35) + large volume (0.20) + counterparty (0.10) + confidence (0.05) = 0.70 → HOT
        assert signal.ai["classification"] == "HOT"
        assert signal.ai["lead_score"] >= 0.70

    def test_news_signal_gets_low_classification(self) -> None:
        """A news signal with no volume/counterparty gets LOW classification."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        signal = _make_signal(
            1,
            kind_value="news",
            volume=None,
            counterparty_text=None,
            scoring_prompt_version="lead_v0",
        )
        # Low confidence to avoid confidence boost
        signal.ai["confidence"] = 0.4
        session = _make_mock_session([signal])

        rescore_on_prompt_version_change(session, new_version=new_version)

        # news (0.05) + no volume (0) + no counterparty (0) + low confidence (0) = 0.05 → LOW
        assert signal.ai["classification"] == "LOW"

    def test_none_ai_signals_are_skipped(self) -> None:
        """Signals with ai=None are skipped (not crashed)."""
        from app.services.lead_score_recompute_service import (  # noqa: PLC0415
            rescore_on_prompt_version_change,
        )

        new_version = "lead_v2"
        signal = _make_signal(1, scoring_prompt_version="lead_v0")
        signal.ai = None  # ai is None (should not happen, but guard it)
        session = _make_mock_session([signal])

        count = rescore_on_prompt_version_change(session, new_version=new_version)

        assert count == 0  # skipped, not crashed
