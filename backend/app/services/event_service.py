"""Transactional-outbox writer (R1 — ARCHITECTURE §5, §7).

Cross-context effects go through the ``domain_events`` outbox: a state change and
its event row are written in the SAME database transaction. ``emit`` only appends
and flushes — the caller owns the commit (or the rollback), so the event is
persisted iff the state change is. The dispatcher
(``app/tasks/events.py::dispatch_domain_events``) later polls unpublished rows and
fans out to idempotent consumers.

    def approve_case(db, case, staff):
        case.status = CaseStatus.approved           # state change
        event_service.emit(db, COMPANY_VERIFIED, "company", case.company_id, {...})
        db.commit()                                 # both, or neither
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.events import DomainEvent

logger = logging.getLogger(__name__)


def emit(
    db: Session,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | int,
    payload: dict[str, object],
) -> None:
    """Append a domain event to the outbox in the caller's transaction.

    Flush-only: never commits. The event lands in the same transaction as the
    state change that produced it, so a caller rollback discards it too.

    Args:
        db: Active session. The caller is responsible for the commit.
        event_type: One of the constants in :mod:`app.services.event_types`
            (stored verbatim in ``domain_events.event_type``).
        aggregate_type: The aggregate root's type (e.g. ``"company"``,
            ``"verification_case"``).
        aggregate_id: The aggregate root's id; coerced to text for storage.
        payload: JSON-serializable event body handed to consumers.
    """
    event = DomainEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        payload=payload,
    )
    db.add(event)
    db.flush()  # assigns event.id; does NOT commit — the caller's transaction owns it
    logger.info(
        "domain_event.emit",
        extra={
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "event_id": event.id,
        },
    )
