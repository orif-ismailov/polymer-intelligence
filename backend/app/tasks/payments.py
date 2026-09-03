"""Payments tasks (R4 / P3 — T1.4; R6 / P7.b — T2.2).

Two directions of causation live here.

**Outbound (P3):**

    DEAL_STATUS_CHANGED (to=contract_signed) → escrow_service.open_for_deal

It exists so that no HTTP handler, and nobody's signature callback, has to
remember to create the payment: the deal reaching `contract_signed` is what
causes the invoice, and the event says so.

**Inbound (P7.b):** `apply_escrow_provider_event` interprets one bank callback
already sitting in the `provider_events` inbox, and `sweep_provider_events` is
the beat that catches whatever the broker dropped between the webhook's commit
and its `apply_async`. Both run on `default` rather than `verify`: they make no
outbound call, they move a deal.

Delivery is at-least-once — the consumer runs before its event is stamped
published, so a crash in between re-delivers. `open_for_deal` is idempotent, and
this consumer never raises: a consumer that throws keeps its event unpublished
and has the dispatcher retry it forever.

Filtering happens here, not at the dispatcher: every deal transition emits
DEAL_STATUS_CHANGED and `CONSUMERS` routes by event type alone, so anything but
`contract_signed` is skipped (the same shape as `notify.send_deal_status_to_group`).

Uniform consumer signature: ``(event_id, aggregate_id, payload)``. `aggregate_id`
is the deal id.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.enums import DealStatus
from app.services import event_types
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="payments.open_escrow_on_deal_signed", queue="default")  # type: ignore[untyped-decorator]
def open_escrow_on_deal_signed(
    event_id: int | None = None, aggregate_id: str | None = None, payload: Any = None
) -> dict[str, Any]:
    """Raise the escrow payment for a deal whose contract was just signed."""
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals.models import Deal  # noqa: PLC0415

    data = payload if isinstance(payload, dict) else {}
    if data.get("to") != DealStatus.contract_signed.value:
        return {"status": "skipped", "reason": "not a contract_signed transition"}

    if aggregate_id is None:
        return {"status": "skipped", "reason": "no deal id"}
    try:
        deal_id = int(aggregate_id)
    except (TypeError, ValueError):
        return {"status": "skipped", "reason": "bad deal id"}

    try:
        with Session(engine) as db:
            deal = db.get(Deal, deal_id)
            if deal is None:
                return {"status": "skipped", "reason": "deal not found"}
            if deal.status != DealStatus.contract_signed:
                # Re-delivery after the escrow already moved the deal on, or a
                # later status change racing ahead. Either way, nothing to do.
                return {
                    "status": "noop",
                    "reason": f"deal is {deal.status.value}",
                    "deal_id": deal.id,
                }

            payment = escrow_service.open_for_deal(db, deal)
            db.commit()
            logger.info(
                "payment_tasks.escrow_opened",
                extra={"deal_id": deal.id, "payment_id": payment.id},
            )
            return {"status": "ok", "deal_id": deal.id, "payment_id": payment.id}
    except escrow_service.DealAmountMissing:
        # Not an error to retry: the deal genuinely has no agreed total, so it
        # waits at contract_signed for staff to fix. Reported loudly (the
        # dashboard escrow queue lists such deals) rather than raised, which
        # would have the dispatcher redeliver forever.
        logger.warning("payment_tasks.escrow_blocked_no_amount", extra={"deal_id": deal_id})
        return {"status": "blocked", "reason": "deal has no amount", "deal_id": deal_id}
    except Exception as exc:  # noqa: BLE001 — a bad consumer must not wedge the outbox
        logger.exception("payment_tasks.escrow_open_failed", extra={"deal_id": deal_id})
        return {"status": "error", "error": str(exc), "deal_id": deal_id}


@celery_app.task(name="payments.apply_escrow_provider_event", queue="default")  # type: ignore[untyped-decorator]
def apply_escrow_provider_event(event_id: int) -> dict[str, Any]:
    """Interpret one recorded bank callback (`escrow_service.apply_provider_event`).

    Never raises. The webhook already answered 200, so the bank will not retry;
    an exception here would only have the sweeper re-attempt a verdict that will
    not change. Everything the service refuses comes back as a `held` result with
    a named reason, which is what the operator queue reads.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals.payment_models import ProviderEvent  # noqa: PLC0415

    try:
        with Session(engine) as db:
            event = db.get(ProviderEvent, event_id)
            if event is None:
                return {"status": "skipped", "reason": "event not found", "event_id": event_id}
            result = escrow_service.apply_provider_event(db, event)
            db.commit()
            logger.info("payment_tasks.provider_event", extra={"event_id": event_id, **result})
            return result
    except Exception as exc:  # noqa: BLE001 — a bad callback must not wedge the rail
        logger.exception("payment_tasks.provider_event_failed", extra={"event_id": event_id})
        return {"status": "error", "error": str(exc), "event_id": event_id}


@celery_app.task(name="sweep_provider_events")  # type: ignore[untyped-decorator]
def sweep_provider_events(limit: int = 100) -> dict[str, Any]:
    """Apply provider callbacks still unprocessed (beat — every 5 minutes).

    The webhook commits the inbox row BEFORE enqueuing the applier, precisely so
    that a Redis blip costs latency rather than evidence. This is the other half
    of that bargain. Idempotent: an already-processed row is not selected, and
    `apply_provider_event` short-circuits on one anyway.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.domains.deals.payment_models import ProviderEvent  # noqa: PLC0415

    processed = 0
    outcomes: dict[str, int] = {}
    with Session(engine) as db:
        pending = (
            db.query(ProviderEvent)
            .filter(ProviderEvent.processed.is_(False))
            .order_by(ProviderEvent.id)
            .limit(limit)
            .all()
        )
        for event in pending:
            try:
                result = escrow_service.apply_provider_event(db, event)
                db.commit()
            except Exception as exc:  # noqa: BLE001 — one bad row must not stop the sweep
                db.rollback()
                logger.exception(
                    "payment_tasks.sweep_item_failed", extra={"event_id": event.id}
                )
                outcomes["error"] = outcomes.get("error", 0) + 1
                del exc
                continue
            processed += 1
            key = str(result.get("status", "unknown"))
            outcomes[key] = outcomes.get(key, 0) + 1

    if processed:
        logger.info(
            "payment_tasks.sweep_provider_events",
            extra={"processed": processed, "outcomes": outcomes},
        )
    return {"processed": processed, "outcomes": outcomes}


@celery_app.task(name="reconcile_escrow_payments", queue="verify")  # type: ignore[untyped-decorator]
def reconcile_escrow_payments(limit: int = 100) -> dict[str, Any]:
    """Ask the bank where each live payment stands (beat — the `verify` queue).

    The only part of the escrow rail that CALLS OUT, hence `verify`: the queue
    exists so a slow or dead provider cannot starve ingest/parse/notify.

    Today this is honestly a no-op — `escrow_mode` ships `stub`, and `live` has
    no adapter until the bank's specification arrives. It reports which of the
    two it is rather than raising or quietly polling the stub, because a stub
    standing in for a bank is exactly the confusion this rail must not create.

    A divergence the rules refuse to apply (the bank released funds on a deal
    nobody confirmed delivered; the bank refunded) raises an admin alert. It is
    never an auto-transition.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.deals import escrow as escrow_service  # noqa: PLC0415
    from app.integrations.escrow import client as escrow_client  # noqa: PLC0415

    try:
        with Session(engine) as db:
            mode = escrow_client.current_mode()
            if mode != escrow_client.MODE_LIVE:
                return {"status": "no_provider", "reason": f"escrow_mode is {mode!r}"}
            try:
                client = escrow_client.get_escrow_client(db)
            except escrow_client.ProviderUnavailable as exc:
                return {"status": "no_provider", "reason": str(exc)}

            report = escrow_service.reconcile_with_provider(db, client, limit=limit)
            db.commit()
    except Exception as exc:  # noqa: BLE001 — a beat that raises just retries the same failure
        logger.exception("payment_tasks.reconcile_failed")
        return {"status": "error", "error": str(exc)}

    held_ids = report.get("held_payment_ids") or []
    if isinstance(held_ids, list) and held_ids:
        _alert_divergence(held_ids, report.get("reasons"))
    logger.info("payment_tasks.reconcile", extra={k: v for k, v in report.items()})
    return {"status": "ok", **report}


def _alert_divergence(payment_ids: list[Any], reasons: Any = None) -> None:
    """Best-effort admin-channel alert on a bank/ledger divergence (never raises).

    Mirrors `app.tasks.contracts._alert_integrity`. Deduplication is upstream: the
    synthesized poll event id is deterministic, so a standing disagreement is
    alerted once and then lives in the operator queue.
    """

    from app.services import settings_service  # noqa: PLC0415

    chat_id = settings_service.verification_chat_id()
    if chat_id is None:
        return
    try:
        import asyncio  # noqa: PLC0415

        from telegram.bot import bot  # noqa: PLC0415

        detail = ", ".join(str(r) for r in (reasons or [])) or "—"
        text = (
            "⚠️ Расхождение эскроу с банком (переход НЕ выполнен автоматически).\n"
            f"Платежи: {', '.join(str(i) for i in payment_ids)}\nПричины: {detail}"
        )
        asyncio.run(bot.send_message(chat_id=chat_id, text=text[:4096]))
    except Exception as exc:  # noqa: BLE001
        logger.error("payment_tasks.reconcile_alert_failed", extra={"error": str(exc)})


def _register_consumers() -> None:
    """Wire DEAL_STATUS_CHANGED to this consumer (idempotent — see events.CONSUMERS)."""
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    if open_escrow_on_deal_signed not in CONSUMERS.get(event_types.DEAL_STATUS_CHANGED, []):
        CONSUMERS[event_types.DEAL_STATUS_CHANGED].append(open_escrow_on_deal_signed)


_register_consumers()
