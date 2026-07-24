"""Transactional-outbox dispatcher (R1 W2 — ARCHITECTURE §5, §7).

``dispatch_domain_events`` (beat, every 15 s) polls unpublished ``domain_events``
rows with ``FOR UPDATE SKIP LOCKED``, fans each out to its registered consumers,
and stamps ``published_at``. SKIP LOCKED lets several beat/worker instances run
concurrently without double-dispatching: each grabs a disjoint batch.

Delivery is **at-least-once** — a consumer is dispatched (via ``apply_async``)
before its event is marked published, so a crash between the two re-delivers on
the next tick. Consumers MUST therefore be idempotent (status-guarded mutations,
re-delivery-tolerant notifications).

``CONSUMERS`` maps ``event_type`` → the tasks to fan out to. Every known
event_type has an entry (an empty list means "acknowledged, no side effects
yet" — R1 wires no consumers; W4 adds verification tasks, W6 the notify cards).
An event whose type is absent from ``CONSUMERS`` is logged as *unroutable* and
skipped — still marked published so a stray type can never wedge the poll loop.
Later waves register consumers by appending to the lists::

    from app.tasks.notify import send_verification_case_to_group
    CONSUMERS[event_types.VERIFICATION_CASE_SUBMITTED].append(send_verification_case_to_group)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.models.events import DomainEvent
from app.services import event_types
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Rows pulled per dispatcher tick. Bounds the FOR UPDATE lock footprint and keeps
# each tick short so concurrent dispatchers stay disjoint via SKIP LOCKED.
_BATCH_SIZE = 200

# event_type → consumer Celery tasks. Empty lists are intentional in R1.
# `dict.get(event_type)` returning None ⇒ unroutable (unknown) type.
CONSUMERS: dict[str, list[Any]] = {event_type: [] for event_type in event_types.ALL_EVENT_TYPES}


def _fan_out(event: DomainEvent) -> bool:
    """Dispatch one event to its consumers.

    Returns ``True`` when the event may be marked published:
      * known type — every consumer dispatched (or none registered), or
      * unknown type — skip it (logged) so it can't wedge the queue.
    Returns ``False`` only when a known consumer's ``apply_async`` raised, so the
    event stays unpublished and the next tick retries it.
    """
    consumers = CONSUMERS.get(event.event_type)
    if consumers is None:
        logger.warning(
            "domain_event.unroutable",
            extra={"event_id": event.id, "event_type": event.event_type},
        )
        return True

    ok = True
    for consumer in consumers:
        try:
            consumer.apply_async(kwargs={"event_id": event.id, "payload": event.payload})
        except Exception:  # noqa: BLE001 — one bad consumer must not abort the batch
            ok = False
            logger.exception(
                "domain_event.dispatch_failed",
                extra={
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "consumer": getattr(consumer, "name", repr(consumer)),
                },
            )
    return ok


@celery_app.task(name="app.tasks.events.dispatch_domain_events")  # type: ignore[untyped-decorator]
def dispatch_domain_events() -> dict[str, int]:
    """Poll unpublished outbox rows, fan out to consumers, stamp published_at.

    Returns a small summary dict (``selected``/``published``) for observability
    and tests.
    """
    from app.core.db import SessionLocal  # noqa: PLC0415

    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(DomainEvent)
                .where(DomainEvent.published_at.is_(None))
                .order_by(DomainEvent.id)
                .limit(_BATCH_SIZE)
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        if not rows:
            return {"selected": 0, "published": 0}

        # Dispatch first, then stamp — at-least-once (see module docstring).
        published_ids = [event.id for event in rows if _fan_out(event)]
        if published_ids:
            db.execute(
                update(DomainEvent)
                .where(DomainEvent.id.in_(published_ids))
                .values(published_at=func.now())
            )
        db.commit()

    return {"selected": len(rows), "published": len(published_ids)}
