"""
FX rate service: idempotent upsert + on-read conversion.

This module provides two functions:
- upsert_fx_rates(session, rates): INSERT ... ON CONFLICT (rate_date, ccy) DO UPDATE SET rate
- convert_amount(session, amount, ccy, on_date): on-read conversion; NEVER writes

Design decisions:
  REQ-fx-rates: Original currency/amount is NEVER stored as converted.
                Conversion is computed on read from fx_rates.
  T-02-15: All Decimal math — never float for money values.
  T-02-16: All SQL uses bound parameters (SQLAlchemy text().bindparams or ORM).

The upsert uses a raw INSERT ... ON CONFLICT because:
1. SQLAlchemy 2 ORM merge() does not natively generate "DO UPDATE" for composite PKs
   without special dialects; using `text()` with bound params is cleaner and explicit.
2. The ON CONFLICT ensures idempotency: re-importing the same day's rates refreshes
   the rate value without creating duplicate rows (REQ-fx-rates daily import).
"""

from __future__ import annotations

import datetime
import decimal
import logging
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.ingest.cbu_rates.adapter import CbuRateRow

logger = logging.getLogger(__name__)


def upsert_fx_rates(session: Session, rates: list[CbuRateRow]) -> int:
    """Insert CBU rate rows into fx_rates, updating on duplicate (rate_date, ccy).

    Uses INSERT ... ON CONFLICT (rate_date, ccy) DO UPDATE SET rate = EXCLUDED.rate
    to ensure re-importing the same day's rates is fully idempotent (no duplicate rows,
    rate value refreshed).

    Args:
        session: Active SQLAlchemy session. Caller is responsible for committing.
        rates: List of CbuRateRow objects to upsert. May be empty (returns 0).

    Returns:
        Number of rows processed (NOT net-new rows; every row in `rates` is counted,
        since ON CONFLICT overwrites the existing value if it differs).

    Security (T-02-16):
        All SQL uses bound parameters — no f-string or format-based SQL.
    """
    if not rates:
        return 0

    for row in rates:
        session.execute(
            text(
                """
                INSERT INTO fx_rates (rate_date, ccy, rate)
                VALUES (:rate_date, :ccy, :rate)
                ON CONFLICT (rate_date, ccy) DO UPDATE SET rate = EXCLUDED.rate
                """
            ),
            {
                "rate_date": row.rate_date,
                "ccy": row.ccy,
                "rate": row.rate,
            },
        )

    logger.info("fx_service.upsert_fx_rates", extra={"count": len(rates)})
    return len(rates)


def convert_amount(
    session: Session,
    amount: decimal.Decimal,
    ccy: str,
    on_date: datetime.date,
) -> decimal.Decimal | None:
    """Convert amount from ccy to UZS using the most recent rate ≤ on_date.

    Performs a SELECT-only query — this function MUST NOT write to fx_rates or
    any other table. The original currency/amount is never mutated (REQ-fx-rates).

    Algorithm:
        SELECT rate FROM fx_rates
        WHERE ccy = :ccy AND rate_date <= :on_date
        ORDER BY rate_date DESC
        LIMIT 1

    Args:
        session: Active SQLAlchemy session (read-only usage).
        amount: The original amount to convert (Decimal).
        ccy: ISO 4217 currency code (e.g. "USD", "CNY", "RUB").
        on_date: The date for rate lookup; uses the most recent rate ≤ this date.

    Returns:
        amount * rate as Decimal if a rate is found, or None if no rate exists
        for the given ccy on or before on_date.

    Security (T-02-15):
        Result is Decimal multiplication — never float arithmetic.
    Security (T-02-16):
        Uses bound parameters (:ccy, :on_date) — no f-string SQL.
    """
    row = session.execute(
        text(
            """
            SELECT rate
            FROM fx_rates
            WHERE ccy = :ccy
              AND rate_date <= :on_date
            ORDER BY rate_date DESC
            LIMIT 1
            """
        ),
        {"ccy": ccy, "on_date": on_date},
    ).fetchone()

    if row is None:
        logger.debug(
            "fx_service.convert_amount.no_rate",
            extra={"ccy": ccy, "on_date": str(on_date)},
        )
        return None

    rate: decimal.Decimal = row[0]

    # Decimal multiplication (T-02-15: never float for money)
    result = amount * rate
    logger.debug(
        "fx_service.convert_amount",
        extra={
            "amount": str(amount),
            "ccy": ccy,
            "on_date": str(on_date),
            "rate": str(rate),
            "result": str(result),
        },
    )
    return result
