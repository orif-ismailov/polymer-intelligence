"""
Showcase prices — a short quote history so the price rails are not empty.

Normally `price_points` is a DERIVED layer: the nightly aggregation over
`kind='deal'` signals, or an external index cron. On an environment where neither
has run — a fresh database, disabled sources, no outbound network — every price
surface answers `200 []` while being perfectly healthy, and there is no way to tell
the empty case from a broken one. There is also **no write endpoint for a price and
there should not be**: a price is an observation, not something a client submits, so
QA cannot create this data through the API at all (IMEX-11).

This writes the derived rows directly, in the shape `storefront.latest_quotes`,
`pricing.analysis` and the dashboard chart already read.

    docker exec <api> python -m app.seed.seed_showcase_prices

**Two observations per product minimum, and that is the point.** `latest_quotes`
returns `change_pct = None` when a product has only one reading — deliberately, so a
new product reads as "no history yet" rather than as a flat market. Seeding one row
per product would leave the field QA needs to verify permanently null, so this writes
a WEEKLY SERIES and the rail shows a real change against the prior week.

Idempotent: every row is attached to a dedicated `manual` source (`_SOURCE_NAME`), and
a re-run deletes that source's rows first. Nothing else in `price_points` is touched,
so this can be run on an environment that also has real ingested prices — unlike
`seed_showcase`, which purges companies, deals and accounts and is not safe to point
at an environment somebody is testing against.

Fixture data, not reference data: it is deliberately NOT in `python -m app.seed`
(see that module's docstring). Invented numbers on a market-intelligence platform are
only ever acceptable when someone has asked for them by name.
"""

from __future__ import annotations

import argparse
import datetime
import decimal
import random
import sys

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import SessionLocal

RNG = random.Random(20260910)

#: The fixture's own source row. `price_points.source_id` is NOT NULL, and pointing
#: these at a real exchange would attribute invented numbers to UZEX. A `manual`
#: source says what they are, and doubles as the delete key for a re-run.
_SOURCE_NAME = "Showcase prices (fixture)"

#: Plausible mid-2026 Uzbek domestic levels, USD/MT. Keyed by `products.code` so a
#: product missing from this deployment's reference data is skipped, not invented.
_BASE_USD: dict[str, int] = {
    "PP": 1180,
    "HDPE": 1240,
    "LDPE": 1310,
    "LLDPE": 1265,
    "PVC": 980,
    "PET": 1090,
    "PS": 1420,
    "ABS": 2150,
}

#: Weekly readings per product. Eight weeks is enough for the rail's change figure
#: and for the chart behind it to have a shape.
_WEEKS = 8

#: The domestic market these readings describe.
_MARKET = "UZ"


def _money(value: float) -> decimal.Decimal:
    return decimal.Decimal(str(round(value, 2)))


def _source_id(db: Session) -> int:
    """The fixture source, created on first run."""
    existing = db.execute(
        sa.text("SELECT id FROM sources WHERE name = :name"), {"name": _SOURCE_NAME}
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)

    return int(
        db.execute(
            sa.text(
                """
                INSERT INTO sources (kind, adapter, name, country, is_enabled, config)
                VALUES ('manual', 'manual', :name, 'UZ', false, '{}'::jsonb)
                RETURNING id
                """
            ),
            {"name": _SOURCE_NAME},
        ).scalar_one()
    )


def seed_prices(db: Session, *, weeks: int = _WEEKS) -> int:
    """Write a weekly quote series per active product. Returns the row count."""
    source_id = _source_id(db)

    # Only this fixture's rows — real ingested prices on the same environment stay.
    db.execute(
        sa.text("DELETE FROM price_points WHERE source_id = :sid"), {"sid": source_id}
    )

    products = db.execute(
        sa.text(
            "SELECT id, code FROM products WHERE is_active ORDER BY sort_order, code"
        )
    ).all()

    today = datetime.date.today()
    rows = 0
    for product_id, code in products:
        base = _BASE_USD.get(str(code))
        if base is None:
            continue

        # A gentle random walk, bounded so eight weeks cannot drift somewhere silly.
        level = float(base)
        for week in range(weeks):
            observed = today - datetime.timedelta(weeks=weeks - 1 - week)
            level *= 1 + RNG.uniform(-0.018, 0.021)
            level = max(base * 0.88, min(base * 1.14, level))
            db.execute(
                sa.text(
                    """
                    INSERT INTO price_points (kind, source_id, product_id, market,
                                              currency, unit, price_avg, price_min,
                                              price_max, volume_total, deals_count,
                                              observed_on)
                    VALUES ('deal_avg', :sid, :product_id, :market, 'USD', 'MT',
                            :avg, :pmin, :pmax, :volume, :deals, :observed)
                    """
                ),
                {
                    "sid": source_id,
                    "product_id": product_id,
                    "market": _MARKET,
                    "avg": _money(level),
                    "pmin": _money(level * 0.971),
                    "pmax": _money(level * 1.028),
                    "volume": _money(RNG.randrange(140, 1850)),
                    "deals": RNG.randrange(2, 17),
                    "observed": observed,
                },
            )
            rows += 1

    db.commit()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed showcase price points.")
    parser.add_argument(
        "--weeks", type=int, default=_WEEKS, help=f"weekly readings per product (default {_WEEKS})"
    )
    args = parser.parse_args()
    if args.weeks < 2:
        # One reading leaves `change_pct` null on every row, which is the thing
        # this seeder exists to make verifiable.
        parser.error("--weeks must be at least 2, or change_pct stays null")

    db = SessionLocal()
    try:
        rows = seed_prices(db, weeks=args.weeks)
    finally:
        db.close()
    print(f"prices: {rows} readings ({args.weeks} weeks per active product, market {_MARKET})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
