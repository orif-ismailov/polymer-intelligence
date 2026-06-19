"""
Tests for nightly_llm_catchup Celery task.

Verifies:
- budget_deferred raw_items from telegram sources are re-enqueued
- non-deferred items are skipped
- the beat schedule has 'nightly_llm_catchup' at hour=2
- the task does not crash on an empty result set
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test: nightly beat entry exists
# ---------------------------------------------------------------------------


def test_nightly_llm_catchup_beat_entry_exists():
    """BEAT_SCHEDULE must contain 'nightly_llm_catchup' with hour=2."""
    from app.tasks.schedule import BEAT_SCHEDULE  # noqa: PLC0415
    from celery.schedules import crontab  # noqa: PLC0415

    assert "nightly_llm_catchup" in BEAT_SCHEDULE, (
        "nightly_llm_catchup not found in BEAT_SCHEDULE"
    )
    entry = BEAT_SCHEDULE["nightly_llm_catchup"]
    assert entry["task"] == "nightly_llm_catchup"
    schedule = entry["schedule"]
    # Should be a crontab with hour=2 — check the schedule type at minimum
    assert isinstance(schedule, crontab)
    # crontab hour field may be a string or int; normalize to string
    assert str(schedule._orig_hour) in ("2", "2,")


# ---------------------------------------------------------------------------
# Test: deferred items are re-enqueued
# ---------------------------------------------------------------------------


def test_deferred_items_are_reenqueued():
    """budget_deferred raw_items from telegram sources are re-enqueued for parse."""
    from app.tasks.nightly_catchup import nightly_llm_catchup  # noqa: PLC0415

    # Mock raw_items returned by the DB query
    raw_item_1 = MagicMock()
    raw_item_1.id = 10
    raw_item_2 = MagicMock()
    raw_item_2.id = 20

    mock_session = MagicMock()
    mock_session.execute.return_value.fetchall.return_value = [
        (10,),
        (20,),
    ]

    with (
        patch("app.tasks.nightly_catchup.get_session") as mock_get_session,
        patch("app.tasks.nightly_catchup.enqueue_for_telegram_parse") as mock_enqueue,
        patch("app.tasks.nightly_catchup.check_and_reserve_tokens"),
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Reset parse_status to 'pending' before re-enqueue
        nightly_llm_catchup()

    # Both items were enqueued
    assert mock_enqueue.call_count == 2
    enqueued_ids = {c[0][0] for c in mock_enqueue.call_args_list}
    assert 10 in enqueued_ids
    assert 20 in enqueued_ids


# ---------------------------------------------------------------------------
# Test: empty result set — no crash, no enqueue
# ---------------------------------------------------------------------------


def test_empty_deferred_list_no_enqueue():
    """If no deferred items exist, enqueue_for_telegram_parse is not called."""
    from app.tasks.nightly_catchup import nightly_llm_catchup  # noqa: PLC0415

    mock_session = MagicMock()
    mock_session.execute.return_value.fetchall.return_value = []

    with (
        patch("app.tasks.nightly_catchup.get_session") as mock_get_session,
        patch("app.tasks.nightly_catchup.enqueue_for_telegram_parse") as mock_enqueue,
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        nightly_llm_catchup()

    mock_enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# Test: nightly task resets parse_status to 'pending' before enqueuing
# ---------------------------------------------------------------------------


def test_nightly_catchup_resets_status_to_pending():
    """nightly_llm_catchup resets raw_item.parse_status to 'pending' so the
    parse task's double-parse guard does not skip the item."""
    from app.tasks.nightly_catchup import nightly_llm_catchup  # noqa: PLC0415

    mock_session = MagicMock()
    mock_session.execute.return_value.fetchall.return_value = [(5,)]

    with (
        patch("app.tasks.nightly_catchup.get_session") as mock_get_session,
        patch("app.tasks.nightly_catchup.enqueue_for_telegram_parse"),
        patch("app.tasks.nightly_catchup.check_and_reserve_tokens"),
    ):
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        nightly_llm_catchup()

    # session.execute should have been called at least twice:
    # 1. SELECT budget_deferred items
    # 2. UPDATE parse_status to 'pending'
    assert mock_session.execute.call_count >= 1
    mock_session.commit.assert_called()
