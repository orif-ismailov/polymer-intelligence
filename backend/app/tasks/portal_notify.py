"""Portal-notification outbox consumers + retention (R2 W2 T2.3).

The transactional outbox (``app/tasks/events.py``) fans cross-context effects out
to idempotent consumers. Here we consume **verification case decisions** and turn
them into in-portal notifications for the affected company's active members.

Request status changes (portal-origin → creator) and inquiry/offer moderation
outcomes are notified **inline** in their services (transactionally); only the
verification decisions — a genuinely separate bounded context — route through the
outbox, mirroring the R1 ``archive_company_offers`` consumer.

Also hosts the ``prune_portal_notifications`` retention beat task (read > 90 d,
unread > 365 d).

Uniform consumer signature: ``(event_id, aggregate_id, payload)``.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from app.services import event_types
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# event_type → the outcome label carried into the notification params. A single
# consumer serves all three decisions; it reloads the event to learn which fired.
_VERIFICATION_OUTCOME: dict[str, str] = {
    event_types.VERIFICATION_CASE_APPROVED: "approved",
    event_types.VERIFICATION_CASE_REJECTED: "rejected",
    event_types.VERIFICATION_CASE_NEEDS_INFO: "needs_info",
}

_RETENTION_READ_DAYS = 90
_RETENTION_UNREAD_DAYS = 365


@celery_app.task(name="notify_company_of_verification_decision", queue="notify")  # type: ignore[untyped-decorator]
def notify_company_of_verification_decision(
    event_id: int | None = None, aggregate_id: str | None = None, payload: Any = None
) -> dict[str, Any]:
    """VERIFICATION_CASE_{APPROVED,REJECTED,NEEDS_INFO} consumer.

    Notifies every active member of the company (kind ``verification_decided``); the
    outcome is derived from the event's type (reloaded by id). Never raises — a bad
    consumer must not wedge the outbox; returns an error dict instead.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    try:
        with Session(engine) as db:
            outcome: str | None = None
            if event_id is not None:
                event = db.get(DomainEvent, event_id)
                if event is not None:
                    outcome = _VERIFICATION_OUTCOME.get(event.event_type)
            if outcome is None:
                return {"status": "skipped", "error": "not a verification decision"}

            company_id = (payload or {}).get("company_id")
            if company_id is None:
                return {"status": "skipped", "error": "no company_id in payload"}

            title_key, body_key = notification_service.keys_for(
                notification_service.KIND_VERIFICATION_DECIDED
            )
            created = notification_service.notify_company(
                db,
                int(company_id),
                kind=notification_service.KIND_VERIFICATION_DECIDED,
                title_key=title_key,
                body_key=body_key,
                params={"outcome": outcome, "case_id": str(aggregate_id)},
                entity="company",
                entity_id=str(company_id),
                # Distinct decisions on one company must not suppress one another, so
                # no unread-dedup here. Re-delivery is bounded (published_at guard).
                dedup=False,
            )
            db.commit()
            return {"status": "ok", "outcome": outcome, "notified": len(created)}
    except Exception as exc:  # noqa: BLE001 — a consumer must never raise into the outbox
        logger.exception(
            "portal_notify.verification_decision.error", extra={"event_id": event_id}
        )
        return {"status": "error", "error": str(exc)}


@celery_app.task(name="prune_portal_notifications")  # type: ignore[untyped-decorator]
def prune_portal_notifications() -> dict[str, Any]:
    """Retention: delete read notifications older than 90 d and unread older than 365 d."""
    from sqlalchemy import delete
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.core.time import utcnow  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415

    now = utcnow()
    read_cutoff = now - datetime.timedelta(days=_RETENTION_READ_DAYS)
    unread_cutoff = now - datetime.timedelta(days=_RETENTION_UNREAD_DAYS)

    with Session(engine) as db:
        deleted_read = db.execute(
            delete(PortalNotification).where(
                PortalNotification.read_at.is_not(None),
                PortalNotification.read_at < read_cutoff,
            )
        ).rowcount
        deleted_unread = db.execute(
            delete(PortalNotification).where(
                PortalNotification.read_at.is_(None),
                PortalNotification.created_at < unread_cutoff,
            )
        ).rowcount
        db.commit()

    logger.info(
        "portal_notify.prune",
        extra={"deleted_read": deleted_read, "deleted_unread": deleted_unread},
    )
    return {"status": "ok", "deleted_read": deleted_read, "deleted_unread": deleted_unread}


def _register_consumers() -> None:
    """Register the verification-decision consumer for all three decision events."""
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    for event_type in _VERIFICATION_OUTCOME:
        if notify_company_of_verification_decision not in CONSUMERS.get(event_type, []):
            CONSUMERS[event_type].append(notify_company_of_verification_decision)


_register_consumers()
