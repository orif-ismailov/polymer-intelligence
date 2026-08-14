"""Outbox consumers that let a contract drive its deal (R4 / P2 — T1.4).

The contracts context (R3) never writes to a deals table. It emits `CONTRACT_*`
domain events; these consumers translate them into deal transitions:

    CONTRACT_SENT       → negotiation      → contract_pending
    CONTRACT_ACTIVATED  → contract_pending → contract_signed
    CONTRACT_DECLINED   ┐
    CONTRACT_CANCELLED  ┘ contract_pending → negotiation

Every one is idempotent because outbox delivery is at-least-once: a consumer
runs before its event is stamped published, so a crash in between re-delivers.
Each therefore checks the deal's CURRENT status and returns a no-op when the
move has already happened — including the late-arriving cancellation that must
not undo a signed deal.

Uniform consumer signature: ``(event_id, aggregate_id, payload)``. `aggregate_id`
is the contract id; the deal is found through `deals.contract_id`.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.enums import DealActorKind, DealStatus
from app.services import event_types
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _advance(contract_id_raw: str | None, to_status: DealStatus, expect: DealStatus) -> dict[str, Any]:
    """Move the deal behind a contract to `to_status`, but only from `expect`.

    Never raises: a consumer that throws would keep its event unpublished and
    have the dispatcher retry it forever.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415

    if contract_id_raw is None:
        return {"status": "skipped", "error": "no contract id"}
    try:
        contract_id = int(contract_id_raw)
    except (TypeError, ValueError):
        return {"status": "skipped", "error": "bad contract id"}

    try:
        with Session(engine) as db:
            deal = deal_service.deal_for_contract(db, contract_id)
            if deal is None:
                # R3 contracts are created outside any deal and still emit these
                # events — that is normal, not an error.
                return {"status": "skipped", "reason": "contract has no deal"}
            if deal.status != expect:
                return {
                    "status": "noop",
                    "reason": f"deal is {deal.status.value}, not {expect.value}",
                    "deal_id": deal.id,
                }

            deal_service.transition(
                db, deal, to_status, actor_kind=DealActorKind.system
            )
            db.commit()
            logger.info(
                "deal_tasks.advance",
                extra={"deal_id": deal.id, "contract_id": contract_id, "to": to_status.value},
            )
            return {"status": "ok", "deal_id": deal.id, "to": to_status.value}
    except Exception as exc:  # noqa: BLE001 — a bad consumer must not wedge the outbox
        logger.exception(
            "deal_tasks.advance_failed",
            extra={"contract_id": contract_id, "to": to_status.value},
        )
        return {"status": "error", "error": str(exc)}


@celery_app.task(name="deals.advance_on_contract_sent", queue="default")  # type: ignore[untyped-decorator]
def advance_deal_on_contract_sent(
    event_id: int | None = None, aggregate_id: str | None = None, payload: Any = None
) -> dict[str, Any]:
    """CONTRACT_SENT → the deal is now waiting on a contract.

    Fires for both `send` and `accept_terms`, which share the event type; the
    second is a no-op because the deal has already left negotiation.
    """
    return _advance(aggregate_id, DealStatus.contract_pending, DealStatus.negotiation)


@celery_app.task(name="deals.advance_on_contract_activated", queue="default")  # type: ignore[untyped-decorator]
def advance_deal_on_contract_activated(
    event_id: int | None = None, aggregate_id: str | None = None, payload: Any = None
) -> dict[str, Any]:
    """CONTRACT_ACTIVATED (both parties signed with E-IMZO) → contract_signed."""
    return _advance(aggregate_id, DealStatus.contract_signed, DealStatus.contract_pending)


@celery_app.task(name="deals.roll_back_on_contract_closed", queue="default")  # type: ignore[untyped-decorator]
def roll_back_deal_on_contract_closed(
    event_id: int | None = None, aggregate_id: str | None = None, payload: Any = None
) -> dict[str, Any]:
    """CONTRACT_DECLINED / CONTRACT_CANCELLED → back to negotiation.

    A rejected draft must not kill the trade: the parties can redraft. Guarded
    on `contract_pending`, so an expiry notice arriving after both signatures
    cannot undo a signed deal.
    """
    return _advance(aggregate_id, DealStatus.negotiation, DealStatus.contract_pending)


def _register_consumers() -> None:
    """Wire the contract events to these consumers (idempotent — see events.CONSUMERS)."""
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    wiring = (
        (event_types.CONTRACT_SENT, advance_deal_on_contract_sent),
        (event_types.CONTRACT_ACTIVATED, advance_deal_on_contract_activated),
        (event_types.CONTRACT_DECLINED, roll_back_deal_on_contract_closed),
        (event_types.CONTRACT_CANCELLED, roll_back_deal_on_contract_closed),
    )
    for event_type, consumer in wiring:
        if consumer not in CONSUMERS.get(event_type, []):
            CONSUMERS[event_type].append(consumer)


_register_consumers()
