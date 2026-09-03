"""
/admin/analytics — what the Didox package and the AI are being spent on.

Read-only, and it writes nothing anywhere: both rails were already journalling
everything this reads. `integration_call_log` has recorded every Didox and E-IMZO
call since R3 and had never been read by anything at all.

Two endpoints rather than one combined payload. They have different natural
windows — the Didox package resets on a calendar month, AI spend is a rolling N
days — and, more usefully, one failing leaves the other on screen. A single query
raising would blank a page whose whole job is to say what is happening.

**Gated on the `appSettings` page, not `is_admin`**, unlike `/admin/llm-spend`.
That grant already carries every runtime rail and the (masked) Didox partner
token; "how many calls did we make" is not the sensitive thing on it. Flip both
to `require_admin` if that reading ever changes — it is one dependency each.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.models.staff import StaffUser
from app.schemas.analytics import AiAnalytics, DidoxAnalytics
from app.services import analytics_service

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


@router.get(
    "/didox",
    response_model=DidoxAnalytics,
    summary="Didox package consumption for the current month",
    description=(
        "Calls made this calendar month (Asia/Tashkent) against the contracted "
        "package, with a month-end projection, a per-operation breakdown, and "
        "provider health for Didox and E-IMZO. Calls refused by our own circuit "
        "breaker are reported as `not_sent` and excluded from consumption — they "
        "never reached Didox and cost no quota."
    ),
)
def get_didox_analytics(
    health_days: int = Query(default=30, ge=1, le=90),
    _current_user: StaffUser = Depends(require_page("appSettings", "read")),
    db: Session = Depends(get_db),
) -> DidoxAnalytics:
    usage = analytics_service.didox_usage(db)
    usage["health"] = analytics_service.provider_health(db, days=health_days)
    return DidoxAnalytics.model_validate(usage)


@router.get(
    "/ai",
    response_model=AiAnalytics,
    summary="LLM token spend by purpose and by model",
    description=(
        "Token spend over the window across all five things the platform uses an "
        "LLM for, plus the degradation panel — errors, budget-deferred items and "
        "rule-based fallbacks. Token and call counts are exact; est_cost_usd uses "
        "the approximate rates echoed in the response."
    ),
)
def get_ai_analytics(
    days: int = Query(default=30, ge=1, le=90),
    _current_user: StaffUser = Depends(require_page("appSettings", "read")),
    db: Session = Depends(get_db),
) -> AiAnalytics:
    usage = analytics_service.ai_usage(db, days=days)
    usage["degradation"] = analytics_service.ai_degradation(db, days=days)
    # Fed from the payload already computed, not from a second pass: recomputing
    # would run the five-table union twice per request and could print a
    # cost-per-outcome that disagrees with the totals printed above it.
    usage["cost_per_outcome"] = analytics_service.cost_per_outcome(
        db,
        days=days,
        didox_spent_uzs=cast(float, analytics_service.didox_usage(db)["spent_uzs"]),
        by_purpose=cast(list[dict[str, object]], usage["by_purpose"]),
    )
    return AiAnalytics.model_validate(usage)
