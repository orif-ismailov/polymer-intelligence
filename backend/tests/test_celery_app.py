"""
Tests for the Celery application configuration.

Verifies:
- The app imports cleanly (no ModuleNotFoundError, no live-broker requirement)
- Queue names exactly match the compose -Q flag: {ingest, parse, notify, default}
- Timezone is Asia/Tashkent with UTC enabled
- Reliability settings: task_acks_late=True, worker_prefetch_multiplier=1
- Serialization: json-only (T-02-01)
"""

from __future__ import annotations


def test_celery_app_imports_cleanly() -> None:
    """app.tasks.celery_app resolves without ModuleNotFoundError or live-broker."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app is not None


def test_queue_names_match_compose_flag() -> None:
    """Queue names must exactly match the compose -Q ingest,parse,notify,default flag."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    queue_names = {q.name for q in celery_app.conf.task_queues}
    assert queue_names == {"ingest", "parse", "notify", "default"}, (
        f"Queue names mismatch: {queue_names!r}"
    )


def test_default_queue_is_default() -> None:
    """Default queue must be 'default' to catch unrouted tasks."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_default_queue == "default"


def test_timezone_is_asia_tashkent() -> None:
    """Celery must use Asia/Tashkent for beat schedule evaluation."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.timezone == "Asia/Tashkent"


def test_utc_enabled() -> None:
    """enable_utc must be True so internal timestamps use UTC."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.enable_utc is True


def test_task_acks_late() -> None:
    """task_acks_late must be True (T-02-02 / REQ-nfr-reliability)."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_acks_late is True


def test_worker_prefetch_multiplier_is_one() -> None:
    """worker_prefetch_multiplier must be 1 (T-02-02 / REQ-nfr-reliability)."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_json_only_serialization() -> None:
    """Serialization must be json-only to refuse pickle (T-02-01)."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert list(celery_app.conf.accept_content) == ["json"]


def test_real_tasks_registered() -> None:
    """All five scheduled task names must be registered by the real implementation modules.

    CR-03: placeholders.py was deleted because it registered the same Celery task
    names as the real implementations (ingest.py, ingest_cbu.py, notify.py).
    The real tasks must now be present in the registry on their own.
    """
    from app.tasks.celery_app import celery_app  # noqa: PLC0415
    import app.tasks.ingest  # noqa: F401, PLC0415 — registers uzex_fetch_* tasks
    import app.tasks.ingest_cbu  # noqa: F401, PLC0415 — registers fetch_cbu_rates
    import app.tasks.notify  # noqa: F401, PLC0415 — registers check_source_health

    required_names = {
        "uzex_fetch_offers",
        "uzex_fetch_contracts",
        "uzex_fetch_deals",
        "fetch_cbu_rates",
        "check_source_health",
    }
    registered = set(celery_app.tasks.keys())
    missing = required_names - registered
    assert not missing, f"Task names not registered: {missing!r}"


def test_task_track_started() -> None:
    """task_track_started must be True for observability."""
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert celery_app.conf.task_track_started is True
