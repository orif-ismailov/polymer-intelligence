"""
Alert rules CRUD + alerts feed endpoints.

Endpoints:
  GET  /alert-rules        — list all rules (staff read)
  POST /alert-rules        — create a rule (admin write)
  PATCH /alert-rules/{id}  — update a rule (admin write)
  GET  /alerts             — alert feed, newest-first (staff read)

Security (T-04-25):
  POST / PATCH require require_admin — non-admin → 403.

Condition validation (T-04-24):
  POST / PATCH body.condition keys are validated against KNOWN_PREDICATE_KEYS.
  Unknown keys raise HTTP 422. Values are stored as JSONB — never executed.

Per-rule delivery channels (D-08):
  channels = [{"type": "telegram_dm", "chat_id": <int>}]
  Stored per rule — no staff-Telegram-linking subsystem in Phase 4.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.alerts.models import Alert, AlertRule
from app.models.enums import AlertKind
from app.models.staff import StaffUser
from app.schemas.dashboard import (
    KNOWN_PREDICATE_KEYS,
    AlertOut,
    AlertRuleCreate,
    AlertRuleOut,
    AlertRulePatch,
)

logger = logging.getLogger(__name__)

# ── Alert Rules router ────────────────────────────────────────────────────────
router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])

# ── Alerts feed router (separate prefix) ─────────────────────────────────────
alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── Helpers ────────────────────────────────────────────────────────────────────


def _validate_condition(condition: dict[str, Any]) -> None:
    """Validate condition keys against the known predicate set.

    Raises HTTP 422 if any unknown key is present (T-04-24).

    Args:
        condition: The condition dict from the request body.
    """
    unknown_keys = set(condition.keys()) - KNOWN_PREDICATE_KEYS
    if unknown_keys:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown predicate keys in condition: {sorted(unknown_keys)}. "
                f"Allowed keys: {sorted(KNOWN_PREDICATE_KEYS)}"
            ),
        )


def _validate_channels(channels: list[dict[str, Any]]) -> None:
    """Validate channels structure: each entry must have 'type' and 'chat_id'.

    Raises HTTP 422 if any channel entry is malformed (D-08).

    Args:
        channels: The channels list from the request body.
    """
    for i, ch in enumerate(channels):
        if "chat_id" not in ch:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Channel[{i}] missing required 'chat_id' field (D-08).",
            )
        if "type" not in ch:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Channel[{i}] missing required 'type' field (D-08).",
            )


def _rule_to_out(rule: AlertRule) -> AlertRuleOut:
    """Convert an AlertRule ORM object to AlertRuleOut schema."""
    return AlertRuleOut(
        id=rule.id,
        kind=rule.kind.value if hasattr(rule.kind, "value") else str(rule.kind),
        name=rule.name,
        condition=rule.condition,
        channels=rule.channels,
        is_enabled=rule.is_enabled,
        created_by=rule.created_by,
        created_at=rule.created_at,
    )


# ── Alert Rules endpoints ──────────────────────────────────────────────────────


@router.get("", response_model=list[AlertRuleOut])
def list_alert_rules(
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: StaffUser = Depends(require_page("alerts", "read")),
) -> list[AlertRuleOut]:
    """List alert rules (staff read).

    Returns up to `limit` rules ordered by created_at descending (max 500).
    Accessible by all staff roles (read-only).
    """
    rules = (
        db.query(AlertRule)
        .order_by(AlertRule.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_rule_to_out(r) for r in rules]


@router.post("", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    body: AlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(require_page("alerts", "write")),
) -> AlertRuleOut:
    """Create a new alert rule (admin write).

    Validates condition keys against the known predicate set (T-04-24).
    Validates channels structure (D-08).
    The rule is disabled by default unless is_enabled=True is explicitly sent.

    Security (T-04-25): require_admin — non-admin → 403.
    """
    _validate_condition(body.condition)
    _validate_channels(body.channels)

    # Validate kind value
    try:
        kind = AlertKind(body.kind)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown alert kind: {body.kind!r}. Valid kinds: {[k.value for k in AlertKind]}",
        ) from None

    rule = AlertRule(
        kind=kind,
        name=body.name,
        condition=body.condition,
        channels=body.channels,
        is_enabled=body.is_enabled,
        created_by=current_user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    logger.info(
        "alert_rules.created",
        extra={"rule_id": rule.id, "admin_id": current_user.id},
    )
    return _rule_to_out(rule)


@router.patch("/{rule_id}", response_model=AlertRuleOut)
def update_alert_rule(
    rule_id: int,
    body: AlertRulePatch,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(require_page("alerts", "write")),
) -> AlertRuleOut:
    """Update an existing alert rule (admin write).

    Validates condition keys and channels structure if provided.

    Security (T-04-25): require_admin — non-admin → 403.
    """
    rule: AlertRule | None = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    if body.name is not None:
        rule.name = body.name

    if body.condition is not None:
        _validate_condition(body.condition)
        rule.condition = body.condition

    if body.channels is not None:
        _validate_channels(body.channels)
        rule.channels = body.channels

    if body.is_enabled is not None:
        rule.is_enabled = body.is_enabled

    db.commit()

    logger.info(
        "alert_rules.updated",
        extra={"rule_id": rule_id, "admin_id": current_user.id},
    )
    return _rule_to_out(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(require_page("alerts", "write")),
) -> None:
    """Delete an alert rule (admin write).

    Permanently removes the rule. Returns 204 No Content on success.

    Security (T-04-25): require_admin — non-admin → 403.

    Raises:
        HTTP 403: Non-admin role.
        HTTP 404: Rule not found.
    """
    rule: AlertRule | None = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    db.delete(rule)
    db.commit()

    logger.info(
        "alert_rules.deleted",
        extra={"rule_id": rule_id, "admin_id": current_user.id},
    )


# ── Alerts feed endpoint ───────────────────────────────────────────────────────


def _alert_to_out(row: Any) -> AlertOut:
    """Convert an Alert ORM object or named-tuple row to AlertOut."""
    return AlertOut(
        id=row.id,
        kind=row.kind.value if hasattr(row.kind, "value") else str(row.kind),
        rule_id=row.rule_id,
        severity=row.severity,
        title=row.title,
        body=row.body,
        signal_id=row.signal_id,
        request_id=row.request_id,
        dedupe_key=row.dedupe_key,
        created_at=row.created_at,
    )


@alerts_router.get("", response_model=list[AlertOut])
def list_alerts(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: StaffUser = Depends(require_page("alerts", "read")),
) -> list[AlertOut]:
    """Alert feed — newest alerts first (staff read).

    Returns up to `limit` most recent alerts.
    Accessible by all staff roles (read-only).

    Timestamps are in UTC (DEC-tz-handling: UTC in DB, Asia/Tashkent on display).
    """
    alerts = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_alert_to_out(a) for a in alerts]
