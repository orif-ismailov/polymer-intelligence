"""Notify matched suppliers about a new RFQ (R4 / P4 — T3.3).

Enqueued fail-soft when a company publishes a purchase request. Gated by the
`rfq_supplier_push_enabled` runtime setting, which ships OFF: a push is
unsolicited mail, so it starts flowing only when an operator says so.

Never raises. A task that throws is retried by Celery, and none of the failures
here are transient — a vanished request, an RFQ with nothing to match on, and a
supplier who already heard are all normal outcomes, reported in the return value.

Deduplication is the schema's job (`uq_rfq_push_target`), not this task's: the
insert is ON CONFLICT DO NOTHING, so a crash halfway through a run is safe to
retry.
"""

from __future__ import annotations

import logging
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="rfq.notify_matched_suppliers", queue="notify")  # type: ignore[untyped-decorator]
def notify_matched_suppliers(request_id: int) -> dict[str, Any]:
    """Tell the top matching suppliers that a buyer wants what they sell."""
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.requests import rfq_push as rfq_push_service  # noqa: PLC0415
    from app.domains.requests import supplier_matching as supplier_matching_service  # noqa: PLC0415
    from app.domains.requests.models import Request  # noqa: PLC0415
    from app.services import (  # noqa: PLC0415
        notification_service,
        settings_service,
    )

    try:
        with Session(engine) as db:
            if not bool(settings_service.get("rfq_supplier_push_enabled")):
                return {"status": "disabled", "request_id": request_id}

            request = db.get(Request, request_id)
            if request is None or request.company_id is None:
                # A Telegram-origin request has no buyer company; suppliers
                # answer company RFQs through the portal, so there is nothing to
                # push. Neither case is retryable.
                return {"status": "skipped", "reason": "no company rfq"}

            top_n = settings_service.get_int("rfq_supplier_push_top_n")
            matches = supplier_matching_service.match_suppliers(db, request)[:top_n]

            title_key, body_key = notification_service.keys_for(
                notification_service.KIND_RFQ_MATCH
            )
            product = request.product_text or request.grade_text or request.polymer_type
            notified = 0
            for match in matches:
                if not rfq_push_service.record_push(
                    db, request.id, match.company_id, score=match.score, rank=match.rank
                ):
                    continue  # already told — see the module docstring
                notification_service.notify_company(
                    db,
                    match.company_id,
                    kind=notification_service.KIND_RFQ_MATCH,
                    title_key=title_key,
                    body_key=body_key,
                    params={
                        "request_id": request.id,
                        "number": request.number,
                        "product": product or "",
                        "volume": str(request.volume) if request.volume is not None else "",
                        "volume_unit": request.volume_unit,
                    },
                    # `rfq`, not `request`: the buyer's request page is
                    # company-scoped, and a supplier cannot open it. This routes
                    # to the supplier's own view of the RFQ, with the CTA on it.
                    entity="rfq",
                    entity_id=str(request.id),
                )
                notified += 1

            db.commit()
            logger.info(
                "rfq_push.done",
                extra={
                    "request_id": request.id,
                    "matched": len(matches),
                    "notified": notified,
                },
            )
            return {
                "status": "ok",
                "request_id": request.id,
                "matched": len(matches),
                "notified": notified,
            }
    except Exception as exc:  # noqa: BLE001 — a retried task must not loop forever
        logger.exception("rfq_push.failed", extra={"request_id": request_id})
        return {"status": "error", "error": str(exc), "request_id": request_id}
