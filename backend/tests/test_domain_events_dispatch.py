"""Unit tests for the outbox dispatcher's routing (R1 W2 — T2.2).

DB-free: exercises ``_fan_out`` (the per-event consumer routing) with a fake
CONSUMERS registry, plus Celery registration/wiring assertions. The full
poll → dispatch → publish path (incl. SKIP LOCKED concurrency) is verified
against a real Postgres in ``test_domain_events_db.py`` (guarded).

App imports are lazy so ``settings`` is only constructed after conftest's
``patch_env`` fixture has run.
"""

from __future__ import annotations

from typing import Any


class _FakeTask:
    """Stand-in for a Celery task: records apply_async kwargs, can simulate a raise."""

    def __init__(self, name: str = "fake.consumer", *, raises: bool = False) -> None:
        self.name = name
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def apply_async(self, *, kwargs: dict[str, Any]) -> None:
        if self.raises:
            raise RuntimeError("broker unavailable")
        self.calls.append(kwargs)


def _event(event_type: str, event_id: int = 1, payload: dict[str, Any] | None = None) -> Any:
    from app.models.events import DomainEvent  # noqa: PLC0415

    event = DomainEvent(
        event_type=event_type,
        aggregate_type="company",
        aggregate_id="1",
        payload=payload if payload is not None else {},
    )
    event.id = event_id  # normally assigned by flush; set explicitly for the unit test
    return event


def test_fan_out_dispatches_registered_consumers_with_event_id_and_payload(monkeypatch) -> None:  # noqa: ANN001
    from app.tasks import events  # noqa: PLC0415

    task = _FakeTask()
    monkeypatch.setattr(events, "CONSUMERS", {"x.type": [task]})

    assert events._fan_out(_event("x.type", 5, {"a": 1})) is True
    assert task.calls == [{"event_id": 5, "aggregate_id": "1", "payload": {"a": 1}}]


def test_fan_out_dispatches_to_every_consumer(monkeypatch) -> None:  # noqa: ANN001
    from app.tasks import events  # noqa: PLC0415

    a, b = _FakeTask("a"), _FakeTask("b")
    monkeypatch.setattr(events, "CONSUMERS", {"x.type": [a, b]})

    assert events._fan_out(_event("x.type", 7)) is True
    assert a.calls and b.calls


def test_fan_out_known_type_with_no_consumers_is_publishable(monkeypatch) -> None:  # noqa: ANN001
    from app.tasks import events  # noqa: PLC0415

    monkeypatch.setattr(events, "CONSUMERS", {"x.type": []})

    assert events._fan_out(_event("x.type")) is True


def test_fan_out_unknown_type_warns_and_is_publishable(monkeypatch, caplog) -> None:  # noqa: ANN001
    from app.tasks import events  # noqa: PLC0415

    monkeypatch.setattr(events, "CONSUMERS", {})

    with caplog.at_level("WARNING"):
        result = events._fan_out(_event("totally.unknown", 9))

    assert result is True  # skipped, but still publishable so it can't wedge the queue
    assert any(r.message == "domain_event.unroutable" for r in caplog.records)


def test_fan_out_consumer_dispatch_failure_defers_event(monkeypatch) -> None:  # noqa: ANN001
    from app.tasks import events  # noqa: PLC0415

    monkeypatch.setattr(events, "CONSUMERS", {"x.type": [_FakeTask(raises=True)]})

    # A failed apply_async ⇒ leave unpublished (return False) so the next tick retries.
    assert events._fan_out(_event("x.type")) is False


# ── Wiring / registration ─────────────────────────────────────────────────────


def test_dispatch_task_is_registered_by_full_name() -> None:
    import app.tasks.events  # noqa: F401, PLC0415 — registers the task
    from app.tasks.celery_app import celery_app  # noqa: PLC0415

    assert "app.tasks.events.dispatch_domain_events" in celery_app.tasks


def test_events_module_listed_in_task_modules() -> None:
    from app.tasks.celery_app import _TASK_MODULES  # noqa: PLC0415

    assert "app.tasks.events" in _TASK_MODULES


def test_consumers_registry_covers_all_event_types() -> None:
    from app.services import event_types  # noqa: PLC0415
    from app.tasks import events  # noqa: PLC0415

    assert set(events.CONSUMERS) == set(event_types.ALL_EVENT_TYPES)
