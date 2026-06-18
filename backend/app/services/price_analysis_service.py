"""
Price analysis service — D-02 real price analysis from price_points.

Phase 4 Plan 04: compute_price_analysis compares a buyer's target_price to
the latest market average from the price_points table for the same product
(market='UZ').

This is NOT an AI computation — it is a direct SQL aggregate on price_points.
D-01 AI fields (match_score, demand_level, recommendation) come back null/
placeholder in Phase 4. D-02 price analysis is computed for real here.

Security:
  Read-only: no INSERT/UPDATE/DELETE, no db.commit().
  Parameters bound via :param syntax (no string interpolation) — T-04-02.
"""

from __future__ import annotations

import decimal
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def compute_price_analysis(
    db: Session,
    product_id: int,
    target_price: decimal.Decimal | None,
    currency: str,
) -> dict | None:
    """Compare target_price to the latest market average from price_points (market='UZ').

    Returns None when:
    - target_price is None (buyer did not specify a target price).
    - No price_points row exists for this product + market='UZ'.

    Otherwise returns a dict with:
    - target_price: float — the buyer's target price.
    - market_avg: float — the latest market average from price_points.
    - delta_pct: float — signed percentage, rounded to 1 decimal place.
                         Positive = target above market (favorable for sellers).
    - label: str — human-readable summary, e.g. "10.0% above market average".

    The function is read-only; it never calls db.commit().

    Args:
        db: Active SQLAlchemy session.
        product_id: The product to look up in price_points.
        target_price: The buyer's stated target price (Decimal or None).
        currency: The currency of the target price (informational; market avg
                  uses the price_points currency for the product).

    Returns:
        dict with target_price/market_avg/delta_pct/label, or None.
    """
    if target_price is None:
        return None

    # Fetch the most recent price_points row for this product + market='UZ'.
    # Uses a parameterised sa.text query — no string interpolation (T-04-02).
    # Index ix_price_points_product_market_observed covers (product_id, market, observed_on).
    row = db.execute(
        sa.text(
            """
            SELECT price_avg, currency
            FROM price_points
            WHERE product_id = :pid AND market = 'UZ'
            ORDER BY observed_on DESC
            LIMIT 1
            """
        ),
        {"pid": product_id},
    ).fetchone()

    if row is None:
        logger.debug(
            "price_analysis_service.no_price_points",
            extra={"product_id": product_id},
        )
        return None

    market_avg = decimal.Decimal(str(row[0]))

    # Guard against zero market average (e.g. product with a recorded zero-price).
    # Decimal raises DivisionByZero / InvalidOperation on 0/0 — return None instead.
    if market_avg == 0:
        logger.debug(
            "price_analysis_service.zero_market_avg",
            extra={"product_id": product_id},
        )
        return None

    # delta_pct: positive means target is above market (buyer willing to pay more)
    delta_pct = float((target_price - market_avg) / market_avg * 100)
    delta_pct_rounded = round(delta_pct, 1)

    abs_pct = abs(delta_pct_rounded)
    direction = "above" if delta_pct_rounded > 0 else "below"
    label = f"{abs_pct:.1f}% {direction} market average"

    logger.debug(
        "price_analysis_service.computed",
        extra={
            "product_id": product_id,
            "target_price": float(target_price),
            "market_avg": float(market_avg),
            "delta_pct": delta_pct_rounded,
        },
    )

    return {
        "target_price": float(target_price),
        "market_avg": float(market_avg),
        "delta_pct": delta_pct_rounded,
        "label": label,
    }
