"""
Tests for the Celery beat schedule.

Verifies that BEAT_SCHEDULE contains all five required entries with the correct
crontab fields matching the dev-spec §2 schedule, all intended to run in the
Asia/Tashkent timezone configured on the celery_app instance.

Note: In Celery 5.x, crontab stores minute/hour/day_of_week as sets (frozensets)
of resolved integer values, not as the original expression strings. Tests
therefore assert on the membership and cardinality of the resolved sets rather
than on the string representation.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def beat_schedule() -> dict[str, dict[str, object]]:
    """Return the BEAT_SCHEDULE dict from app.tasks.schedule."""
    from app.tasks.schedule import BEAT_SCHEDULE  # noqa: PLC0415

    return BEAT_SCHEDULE


def test_all_five_keys_present(beat_schedule: dict[str, dict[str, object]]) -> None:
    """BEAT_SCHEDULE must contain all scheduled task entries.

    Phase 5 (05-02) adds check_userbot_health.
    Phase 5 (05-04) adds nightly_llm_catchup for budget-deferred Telegram items.
    """
    required_keys = {
        # R1 W2: transactional-outbox dispatcher (every 15 s)
        "app.tasks.events.dispatch_domain_events",
        "uzex_fetch_offers",
        "uzex_fetch_contracts",
        "uzex_fetch_deals",
        # Phase 6: xarid buy-side procurement tenders (every 30 min)
        "xarid_fetch_tenders",
        "fetch_cbu_rates",
        # Phase 6: hourly no-code adapter fetch drivers
        "html_table_fetch",
        "llm_page_fetch",
        # Phase 8f-2: RSS is now dispatched dynamically at a configurable interval
        "news_fetch_dispatch",
        "check_source_health",
        # Phase 5 (05-02): userbot heartbeat health check — ROADMAP SC#1 liveness
        "check_userbot_health",
        # Phase 5 (05-04): nightly LLM catch-up for budget-deferred items — ROADMAP SC#4
        "nightly_llm_catchup",
        "generate_daily_report",
        # Phase 8c: evening brief (18:00) + immediate breaking-news publisher
        "generate_evening_report",
        "publish_breaking_news",
        # R2 W2 T2.3: portal notification retention (daily)
        "prune_portal_notifications",
        # R3 TB4.1/TB4.2: contract PDF integrity + stale-contract expiry (daily)
        "verify_contract_integrity",
        "expire_stale_contracts",
        # R6 P7.b T2.2: escrow provider-callback inbox sweep (every 5 min) — the
        # webhook commits its row before enqueuing, so a dropped dispatch costs
        # latency, not evidence. This is what collects it.
        "sweep_provider_events",
        # R6 P7.b T3.1: escrow ↔ bank reconciliation (every 30 min, `verify` queue)
        "reconcile_escrow_payments",
    }
    assert set(beat_schedule.keys()) == required_keys, (
        f"Beat schedule keys mismatch: {set(beat_schedule.keys())!r}"
    )


def test_uzex_fetch_offers_task_name(beat_schedule: dict[str, dict[str, object]]) -> None:
    """uzex_fetch_offers entry must reference the correct contract task name."""
    assert beat_schedule["uzex_fetch_offers"]["task"] == "uzex_fetch_offers"


def test_uzex_fetch_offers_minute(beat_schedule: dict[str, dict[str, object]]) -> None:
    """uzex_fetch_offers must run every 15 minutes.

    crontab(minute='*/15') resolves to {0, 15, 30, 45}.
    """
    from celery.schedules import crontab  # noqa: PLC0415

    sched = beat_schedule["uzex_fetch_offers"]["schedule"]
    assert isinstance(sched, crontab)
    # Resolved set: every 15 minutes in [0, 60) → {0, 15, 30, 45}
    assert sched.minute == {0, 15, 30, 45}, (
        f"Expected minutes {{0, 15, 30, 45}}, got {sched.minute!r}"
    )


def test_uzex_fetch_offers_hour(beat_schedule: dict[str, dict[str, object]]) -> None:
    """uzex_fetch_offers must run only during business hours 9-18.

    crontab(hour='9-18') resolves to {9, 10, 11, 12, 13, 14, 15, 16, 17, 18}.
    """
    from celery.schedules import crontab  # noqa: PLC0415

    sched = beat_schedule["uzex_fetch_offers"]["schedule"]
    assert isinstance(sched, crontab)
    expected_hours = set(range(9, 19))  # 9 through 18 inclusive
    assert sched.hour == expected_hours, (
        f"Expected hours {expected_hours!r}, got {sched.hour!r}"
    )


def test_uzex_fetch_offers_day_of_week(beat_schedule: dict[str, dict[str, object]]) -> None:
    """uzex_fetch_offers must run only on weekdays (mon-fri).

    crontab(day_of_week='mon-fri') resolves to {1, 2, 3, 4, 5}
    where Monday=1, Friday=5.
    """
    from celery.schedules import crontab  # noqa: PLC0415

    sched = beat_schedule["uzex_fetch_offers"]["schedule"]
    assert isinstance(sched, crontab)
    expected_days = {1, 2, 3, 4, 5}  # Mon=1 through Fri=5
    assert sched.day_of_week == expected_days, (
        f"Expected weekdays {expected_days!r}, got {sched.day_of_week!r}"
    )


def test_uzex_fetch_contracts_hourly(beat_schedule: dict[str, dict[str, object]]) -> None:
    """uzex_fetch_contracts must run every hour (minute 0).

    crontab(minute=0) resolves to {0}.
    """
    from celery.schedules import crontab  # noqa: PLC0415

    sched = beat_schedule["uzex_fetch_contracts"]["schedule"]
    assert isinstance(sched, crontab)
    assert 0 in sched.minute, f"Minute 0 must be in {sched.minute!r}"
    assert len(sched.minute) == 1, (
        f"Hourly task should fire only at minute 0, got {sched.minute!r}"
    )


def test_uzex_fetch_deals_hourly(beat_schedule: dict[str, dict[str, object]]) -> None:
    """uzex_fetch_deals must run every hour (minute 0).

    crontab(minute=0) resolves to {0}.
    """
    from celery.schedules import crontab  # noqa: PLC0415

    sched = beat_schedule["uzex_fetch_deals"]["schedule"]
    assert isinstance(sched, crontab)
    assert 0 in sched.minute, f"Minute 0 must be in {sched.minute!r}"
    assert len(sched.minute) == 1, (
        f"Hourly task should fire only at minute 0, got {sched.minute!r}"
    )


def test_fetch_cbu_rates_daily_at_hour_7(beat_schedule: dict[str, dict[str, object]]) -> None:
    """fetch_cbu_rates must run daily at 07:00 Tashkent.

    crontab(minute=0, hour=7) resolves to minute={0}, hour={7}.
    """
    from celery.schedules import crontab  # noqa: PLC0415

    sched = beat_schedule["fetch_cbu_rates"]["schedule"]
    assert isinstance(sched, crontab)
    assert 7 in sched.hour and len(sched.hour) == 1, (
        f"CBU rates must run only at hour 7, got {sched.hour!r}"
    )
    assert 0 in sched.minute and len(sched.minute) == 1, (
        f"CBU rates must run at minute 0, got {sched.minute!r}"
    )


def test_check_source_health_every_5_minutes(
    beat_schedule: dict[str, dict[str, object]],
) -> None:
    """check_source_health must run every 5 minutes.

    crontab(minute='*/5') resolves to {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}.
    """
    from celery.schedules import crontab  # noqa: PLC0415

    sched = beat_schedule["check_source_health"]["schedule"]
    assert isinstance(sched, crontab)
    expected_minutes = set(range(0, 60, 5))  # {0, 5, 10, ..., 55}
    assert sched.minute == expected_minutes, (
        f"Expected every-5-minute set {expected_minutes!r}, got {sched.minute!r}"
    )


def test_dispatch_domain_events_every_15_seconds(
    beat_schedule: dict[str, dict[str, object]],
) -> None:
    """The outbox dispatcher runs on a 15-second timedelta interval (R1 W2)."""
    from datetime import timedelta  # noqa: PLC0415

    entry = beat_schedule["app.tasks.events.dispatch_domain_events"]
    assert entry["task"] == "app.tasks.events.dispatch_domain_events"
    assert entry["schedule"] == timedelta(seconds=15)


def test_all_task_names_match_keys(beat_schedule: dict[str, dict[str, object]]) -> None:
    """Each beat entry's 'task' value must match the schedule dict key (contract name)."""
    for key, entry in beat_schedule.items():
        assert entry["task"] == key, (
            f"Entry {key!r} has task name {entry['task']!r} — must match the key"
        )
