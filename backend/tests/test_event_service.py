"""Unit tests for the transactional-outbox writer (R1 W2 — T2.1).

These are DB-free: they assert the ``emit`` contract (append + flush, NEVER
commit) against a mock session, plus the stability of the event-type vocabulary.
The rolled-back-transaction-leaves-nothing behaviour is verified against a real
Postgres in ``test_domain_events_db.py`` (guarded).

App imports are lazy (inside the test bodies) so that constructing ``settings``
is deferred until after conftest's ``patch_env`` fixture has run — module-level
app imports would trigger ``Settings()`` at collection time and fail validation.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def test_emit_appends_domain_event_and_flushes_without_commit() -> None:
    """emit must db.add a DomainEvent and db.flush — and must NOT commit."""
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_service, event_types  # noqa: PLC0415

    db = MagicMock()

    event_service.emit(
        db,
        event_types.COMPANY_REGISTERED,
        "company",
        42,
        {"tax_id": "123456789"},
    )

    assert db.add.call_count == 1
    added = db.add.call_args.args[0]
    assert isinstance(added, DomainEvent)
    assert added.event_type == event_types.COMPANY_REGISTERED
    assert added.aggregate_type == "company"
    assert added.aggregate_id == "42"  # int coerced to text
    assert added.payload == {"tax_id": "123456789"}

    db.flush.assert_called_once()
    db.commit.assert_not_called()


def test_emit_coerces_int_aggregate_id_to_str() -> None:
    """aggregate_id is stored as Text — ints must be coerced."""
    from app.services import event_service, event_types  # noqa: PLC0415

    db = MagicMock()

    event_service.emit(db, event_types.COMPANY_VERIFIED, "company", 7, {})

    assert db.add.call_args.args[0].aggregate_id == "7"


def test_emit_preserves_string_aggregate_id() -> None:
    from app.services import event_service, event_types  # noqa: PLC0415

    db = MagicMock()

    event_service.emit(db, event_types.COMPANY_VERIFIED, "company", "uuid-abc", {})

    assert db.add.call_args.args[0].aggregate_id == "uuid-abc"


def test_emit_returns_none() -> None:
    """The documented signature is -> None (fire-and-forget into the outbox)."""
    from app.services import event_service, event_types  # noqa: PLC0415

    db = MagicMock()

    result = event_service.emit(db, event_types.COMPANY_REGISTERED, "company", "x", {})

    assert result is None


# ── Event-type vocabulary ─────────────────────────────────────────────────────


def test_event_type_values_are_unique_nonempty_strings() -> None:
    from app.services import event_types  # noqa: PLC0415

    names = [n for n in dir(event_types) if n.isupper() and n != "ALL_EVENT_TYPES"]
    values = [getattr(event_types, n) for n in names]
    assert values, "expected some event-type constants"
    assert all(isinstance(v, str) and v for v in values)
    assert len(values) == len(set(values)), "event-type values must be unique"


def test_all_event_types_covers_every_constant() -> None:
    from app.services import event_types  # noqa: PLC0415

    names = [n for n in dir(event_types) if n.isupper() and n != "ALL_EVENT_TYPES"]
    values = {getattr(event_types, n) for n in names}
    assert values == event_types.ALL_EVENT_TYPES
