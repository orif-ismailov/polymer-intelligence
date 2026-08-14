"""
Price series endpoint.

Endpoint:
  GET /prices/series — price_points series per product/market with date-range
                       and automatic downsampling (>1yr → weekly aggregate per
                       dev-spec §3.1).

Security (T-04-27):
  sa.text with bound params for product_id / market / date range filters.
  No string interpolation into SQL — all values via :param binding.

Downsampling (REQ-price-trends / dev-spec §3.1):
  - Range ≤ 1 year: daily data points returned as-is.
  - Range > 1 year: weekly aggregate (date_trunc('week', observed_on)) with
    AVG(price_avg) for each week to reduce points from ~365+ to ~52+ per year.
"""

from __future__ import annotations

import datetime
import decimal
import logging
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff_user
from app.core.db import get_db
from app.schemas.dashboard import PriceSeriesOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prices", tags=["prices"], dependencies=[Depends(get_current_staff_user)])

# Threshold for switching from daily to weekly downsampling (dev-spec §3.1)
_DOWNSAMPLE_THRESHOLD_DAYS = 365


@router.get("/series", response_model=list[PriceSeriesOut])
def get_price_series(
    product_id: int | None = Query(default=None, description="Filter by product ID"),
    market: str | None = Query(default=None, description="Market filter: UZ, CBU, All"),
    date_from: datetime.date | None = Query(default=None, description="Start date (inclusive)"),
    date_to: datetime.date | None = Query(default=None, description="End date (inclusive)"),
    db: Session = Depends(get_db),
) -> list[PriceSeriesOut]:
    """Return price_points series for the given filters.

    Automatically applies weekly aggregate downsampling when the requested
    date range exceeds 1 year (dev-spec §3.1 REQ-price-trends).

    Security (T-04-27): All filter values are bound parameters — no string
    interpolation into SQL.

    Args:
        product_id: Filter by product ID (optional).
        market: Market filter — 'UZ', 'CBU', or None for all (optional).
        date_from: Start date inclusive (optional).
        date_to: End date inclusive (optional).

    Returns:
        List of PriceSeriesOut data points ordered by observed date ascending.
    """
    # Determine if weekly downsampling should be applied
    use_weekly = False
    if date_from is not None and date_to is not None:
        delta_days = (date_to - date_from).days
        use_weekly = delta_days > _DOWNSAMPLE_THRESHOLD_DAYS

    params: dict[str, Any] = {}

    if use_weekly:
        # Weekly aggregate: AVG(price_avg) per week per currency
        # Uses date_trunc('week', observed_on) to group by ISO week
        # Security (T-04-27): all values bound via :param — never interpolated
        sql = """
            SELECT
                date_trunc('week', observed_on)::date AS observed_on,
                AVG(price_avg) AS price_avg,
                currency
            FROM price_points
            WHERE 1=1
        """
    else:
        # Daily: return rows as-is
        sql = """
            SELECT
                observed_on,
                price_avg,
                currency
            FROM price_points
            WHERE 1=1
        """

    # Build dynamic WHERE clauses with bound params (T-04-27)
    if product_id is not None:
        sql += " AND product_id = :product_id"
        params["product_id"] = product_id

    if market is not None and market.lower() != "all":
        sql += " AND market = :market"
        params["market"] = market

    if date_from is not None:
        sql += " AND observed_on >= :date_from"
        params["date_from"] = date_from

    if date_to is not None:
        sql += " AND observed_on <= :date_to"
        params["date_to"] = date_to

    if use_weekly:
        sql += " GROUP BY date_trunc('week', observed_on), currency"
        sql += " ORDER BY date_trunc('week', observed_on) ASC"
    else:
        sql += " ORDER BY observed_on ASC"

    rows = db.execute(sa.text(sql), params).fetchall()

    return [
        PriceSeriesOut(
            observed_on=row.observed_on,
            price_avg=decimal.Decimal(str(row.price_avg)),
            currency=row.currency,
        )
        for row in rows
    ]
