"""
Alert service — JSONB predicate interpreter + alert/delivery dispatch.

Implements:
  evaluate_condition(condition, entity): hardcoded per-key interpreter,
    NEVER uses dynamic code execution (T-04-24 security requirement).
  evaluate_alert_rules(db, signal_id, request_id): iterates enabled rules,
    creates Alert + Delivery rows with dedupe via IntegrityError catch,
    enqueues send_delivery on the notify queue.
  _load_entity(db, signal_id, request_id): loads Signal or Request from DB.
  _format_body(entity): formats alert body text from entity fields.

Security (T-04-24):
  - Hardcoded per-key dispatch — NEVER dynamic code execution
  - condition keys matched against known set; unknown keys ignored
  - All values passed as ORM/SQLAlchemy attributes, never interpolated into SQL

Service-never-commits axiom:
  All functions call db.flush() to obtain IDs but NEVER call db.commit().
  The caller (router or Celery task) owns the commit.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.alerts import Alert, AlertRule, Delivery
from app.models.enums import DeliveryChannel, DeliveryStatus

logger = logging.getLogger(__name__)


# ── Predicate interpreter ──────────────────────────────────────────────────────


def evaluate_condition(condition: dict[str, Any], entity: Any) -> bool:
    """Hardcoded JSONB predicate interpreter. NEVER uses dynamic code execution.

    Returns True if the entity matches all predicates in condition.
    Returns False if any predicate fails.
    Unknown keys are silently ignored (forward-compatible).

    Security (T-04-24): condition keys are checked against a hardcoded set;
    values are read from the entity via attribute access, never interpolated
    into SQL or dynamically executed.

    Predicate set (Phase 4):
      kind         (list[str]):   entity.kind in list
      product_id   (list[int]):   entity.product_id in list
      volume_gte   (float):       entity.volume >= threshold
      urgency_in   (list[str]):   entity.urgency.value in list
      source_kind  (list[str]):   entity.source_kind in list
      lead_score_gte (float):     (entity.ai or {}).get("lead_score") >= threshold
                                   — always False in Phase 4 (D-07: lead_score is None)

    Args:
        condition: JSONB dict from alert_rules.condition column.
        entity: ORM Signal or Request object with the relevant attributes.

    Returns:
        True if all present predicates match; False otherwise.
    """
    # kind: entity.kind must be in the list
    if "kind" in condition:
        entity_kind = entity.kind
        # Handle StrEnum — compare value string
        if hasattr(entity_kind, "value"):
            entity_kind = entity_kind.value
        if entity_kind not in condition["kind"]:
            return False

    # product_id: entity.product_id must be in the list
    if "product_id" in condition:
        if entity.product_id not in condition["product_id"]:
            return False

    # volume_gte: entity.volume must be >= threshold
    if "volume_gte" in condition:
        if entity.volume is None or entity.volume < condition["volume_gte"]:
            return False

    # urgency_in: entity.urgency.value must be in the list
    if "urgency_in" in condition:
        urgency_val = entity.urgency.value if entity.urgency else None
        if urgency_val not in condition["urgency_in"]:
            return False

    # source_kind: entity.source_kind must be in the list
    if "source_kind" in condition:
        if entity.source_kind not in condition["source_kind"]:
            return False

    # lead_score_gte: (entity.ai or {}).get("lead_score") >= threshold
    # Phase 4 (D-07): lead_score is None for all entities — this predicate never matches.
    # The branch is authored here so rules with lead_score_gte can be saved; they
    # simply never fire until Phase 5 populates ai.lead_score.
    if "lead_score_gte" in condition:
        lead_score = (entity.ai or {}).get("lead_score")
        if lead_score is None or lead_score < condition["lead_score_gte"]:
            return False

    return True


# ── Entity loader ─────────────────────────────────────────────────────────────


def _load_entity(
    db: Session,
    signal_id: int | None,
    request_id: int | None,
) -> Any:
    """Load the Signal or Request entity from the database.

    Args:
        db: SQLAlchemy session.
        signal_id: ID of the Signal to load, or None.
        request_id: ID of the Request to load, or None.

    Returns:
        The loaded ORM object.

    Raises:
        ValueError: If neither signal_id nor request_id is provided, or the entity
            is not found.
    """
    if signal_id is not None:
        from app.models.signals import Signal  # noqa: PLC0415
        entity = db.get(Signal, signal_id)
        if entity is None:
            raise ValueError(f"Signal {signal_id} not found")
        return entity
    elif request_id is not None:
        from app.models.requests import Request  # noqa: PLC0415
        entity = db.get(Request, request_id)
        if entity is None:
            raise ValueError(f"Request {request_id} not found")
        return entity
    else:
        raise ValueError("Either signal_id or request_id must be provided")


# ── Alert body formatter ──────────────────────────────────────────────────────


def _format_body(entity: Any) -> str:
    """Format a human-readable alert body from the entity fields.

    Args:
        entity: ORM Signal or Request object.

    Returns:
        Human-readable description string for the alert body.
    """
    parts: list[str] = []

    kind = getattr(entity, "kind", None)
    if kind is not None:
        kind_val = kind.value if hasattr(kind, "value") else str(kind)
        parts.append(f"Kind: {kind_val}")

    product_id = getattr(entity, "product_id", None)
    if product_id is not None:
        parts.append(f"Product ID: {product_id}")

    volume = getattr(entity, "volume", None)
    if volume is not None:
        parts.append(f"Volume: {volume}")

    urgency = getattr(entity, "urgency", None)
    if urgency is not None:
        urgency_val = urgency.value if hasattr(urgency, "value") else str(urgency)
        parts.append(f"Urgency: {urgency_val}")

    return "; ".join(parts) if parts else "Alert triggered"


# ── Main evaluation function ──────────────────────────────────────────────────


def evaluate_alert_rules(
    db: Session,
    signal_id: int | None = None,
    request_id: int | None = None,
) -> None:
    """Evaluate all enabled alert rules against the given entity.

    For each matching rule:
    1. Creates an Alert row with dedupe_key = 'rule:{rule_id}:{entity_type}:{entity_id}'.
    2. Uses db.flush() + IntegrityError catch for dedupe (ON CONFLICT on uq_alerts_dedupe_key).
    3. Creates one Delivery row per entry in rule.channels.
    4. Enqueues send_delivery.apply_async(args=[alert.id], queue="notify").

    Service-never-commits: only db.flush() — caller owns db.commit().

    Security (T-04-26): Dedupe key collapses duplicate rule+entity alerts;
    all deliveries funnel through the single notify queue with the token-bucket
    rate limiter (25 msg/s bot, 1 msg/s chat_id per D-09 / Pitfall 7).

    Args:
        db: SQLAlchemy session (service-never-commits: only db.flush() called here).
        signal_id: ID of the Signal entity to evaluate rules against (or None).
        request_id: ID of the Request entity to evaluate rules against (or None).
    """
    entity = _load_entity(db, signal_id, request_id)
    entity_type = "signal" if signal_id is not None else "request"
    entity_id = signal_id if signal_id is not None else request_id

    # Load all enabled rules
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.is_enabled == True)  # noqa: E712
        .all()
    )

    for rule in rules:
        if not evaluate_condition(rule.condition, entity):
            continue

        dedupe_key = f"rule:{rule.id}:{entity_type}:{entity_id}"

        alert = Alert(
            kind=rule.kind,
            rule_id=rule.id,
            severity="info",
            title=f"Alert: {rule.name}",
            body=_format_body(entity),
            signal_id=signal_id,
            request_id=request_id,
            dedupe_key=dedupe_key,
        )

        # Use a SAVEPOINT so that a duplicate-key IntegrityError only rolls back
        # this alert insert, not the caller's entire transaction.
        # (Service-never-commits: db.rollback() on the shared session would wipe
        # everything the caller wrote before calling evaluate_alert_rules — CR-02.)
        try:
            with db.begin_nested():   # SAVEPOINT
                db.add(alert)
                db.flush()  # get alert.id; raises IntegrityError on duplicate dedupe_key
        except IntegrityError:
            logger.info(
                "alert_service.dedupe_skip",
                extra={"rule_id": rule.id, "entity_type": entity_type, "entity_id": entity_id},
            )
            continue

        # Create one Delivery per channel in rule.channels
        for channel_config in rule.channels:
            delivery = Delivery(
                alert_id=alert.id,
                channel=channel_config.get("type", DeliveryChannel.telegram_dm),
                recipient=str(channel_config["chat_id"]),
                status=DeliveryStatus.queued,
            )
            db.add(delivery)

        db.flush()

        # Enqueue on the existing notify queue (D-09 / Pitfall 7: NEVER a separate queue)
        # Lazy import per DEC-lazy-notify-import: avoids circular imports at module level
        # and keeps module import socket-free for pytest collection.
        from app.tasks.notify import send_delivery  # noqa: PLC0415

        send_delivery.apply_async(args=[alert.id], queue="notify")

        logger.info(
            "alert_service.dispatched",
            extra={
                "rule_id": rule.id,
                "alert_id": alert.id,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )
