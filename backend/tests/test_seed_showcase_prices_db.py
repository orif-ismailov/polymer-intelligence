"""The showcase price fixture, against a real database (IMEX-11).

Two properties are worth a test, and neither is about the numbers.

**A re-run must not double the series.** This seeder exists to be pointed at an
environment somebody is already testing against, so it deletes only its own rows —
keyed on a dedicated `manual` source — rather than truncating `price_points` the way
`seed_showcase` truncates half the schema.

**Every product must come out with a non-null `change_pct`.** That is the field QA
could not verify while the table was empty, and it is null by design for a product
with a single reading. One row per product would satisfy "prices exist" and still
leave the thing under test unobservable, so the series is the deliverable, not the
row count.

Real-DB only: the query under test is a window function over a self-join, which a
mock cannot answer. Skipped in CI like the rest of the localhost-`test_polymer` set.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def db(engine: sa.Engine):  # noqa: ANN201
    """A catalogue and an empty `price_points`, per test.

    `clean()` does NOT truncate `price_points` or `sources` — it is the shared
    verification-suite helper and neither table is part of that story. Left to it,
    one test's readings become another's price HISTORY, which is invisible until a
    test asserts on `change_pct` and gets a number where it expected null. Cleared
    here rather than widened there: this module is the only one that cares.
    """
    clean(engine)
    session = session_factory(engine)
    with session() as s:
        s.execute(sa.text("DELETE FROM price_points"))
        s.execute(sa.text("DELETE FROM sources"))
        # Products are reference data the fixture keys off; the seeder skips a
        # product it has no base price for, so an empty catalogue means no rows.
        from app.seed.seed_reference import seed_all  # noqa: PLC0415

        seed_all(s)
        s.commit()
        yield s
    clean(engine)


@requires_real_db
def test_it_writes_a_series_per_active_product(db) -> None:  # noqa: ANN001
    from app.seed.seed_showcase_prices import seed_prices  # noqa: PLC0415

    rows = seed_prices(db, weeks=4)
    assert rows > 0

    per_product = db.execute(
        sa.text(
            "SELECT product_id, count(*) FROM price_points GROUP BY product_id"
        )
    ).all()
    assert per_product, "no price points written"
    assert all(count == 4 for _, count in per_product), per_product


@requires_real_db
def test_a_rerun_replaces_rather_than_appends(db) -> None:  # noqa: ANN001
    from app.seed.seed_showcase_prices import seed_prices  # noqa: PLC0415

    first = seed_prices(db, weeks=4)
    second = seed_prices(db, weeks=4)

    total = db.execute(sa.text("SELECT count(*) FROM price_points")).scalar_one()
    assert first == second == total, "a re-run doubled the series"


@requires_real_db
def test_it_leaves_prices_it_did_not_write_alone(db) -> None:  # noqa: ANN001
    """The reason this is not `seed_showcase`: real ingested rows must survive."""
    from app.seed.seed_showcase_prices import seed_prices  # noqa: PLC0415

    other_source = db.execute(
        sa.text(
            """
            INSERT INTO sources (kind, adapter, name, is_enabled, config)
            VALUES ('exchange', 'uzex_deals', 'Real feed', true, '{}'::jsonb)
            RETURNING id
            """
        )
    ).scalar_one()
    product_id = db.execute(sa.text("SELECT id FROM products LIMIT 1")).scalar_one()
    db.execute(
        sa.text(
            """
            INSERT INTO price_points (kind, source_id, product_id, market, currency,
                                      unit, price_avg, observed_on)
            VALUES ('deal_avg', :sid, :pid, 'UZ', 'USD', 'MT', 999.00, CURRENT_DATE)
            """
        ),
        {"sid": other_source, "pid": product_id},
    )
    db.commit()

    seed_prices(db, weeks=3)
    seed_prices(db, weeks=3)

    survivors = db.execute(
        sa.text("SELECT count(*) FROM price_points WHERE source_id = :sid"),
        {"sid": other_source},
    ).scalar_one()
    assert survivors == 1, "the fixture deleted a price it did not write"


@requires_real_db
def test_every_quote_carries_a_change_the_rail_can_show(db) -> None:  # noqa: ANN001
    """`change_pct` null on every row would leave IMEX-11 exactly where it started."""
    from app.domains.storefront import service as public_market_service  # noqa: PLC0415
    from app.seed.seed_showcase_prices import seed_prices  # noqa: PLC0415

    seed_prices(db, weeks=4)

    quotes = public_market_service.latest_quotes(db, limit=40)
    assert quotes, "the public rail is still empty"
    assert all(q.change_pct is not None for q in quotes), [
        (q.code, q.change_pct) for q in quotes
    ]
    # The fields QA enumerated, present and typed.
    for q in quotes:
        assert q.product_id > 0
        assert q.code and q.currency == "USD" and q.unit == "MT"
        assert q.price > 0
        assert q.observed_on is not None


@requires_real_db
def test_one_week_is_refused_because_it_would_publish_null_changes(db) -> None:  # noqa: ANN001
    """The CLI guard, at the level it is enforced — `--weeks 1` is a footgun."""
    from app.domains.storefront import service as public_market_service  # noqa: PLC0415
    from app.seed.seed_showcase_prices import seed_prices  # noqa: PLC0415

    seed_prices(db, weeks=1)
    quotes = public_market_service.latest_quotes(db, limit=40)

    assert quotes, "one reading per product should still populate the rail"
    assert all(q.change_pct is None for q in quotes), (
        "a single reading must read as 'no history yet', which is why the CLI "
        "refuses --weeks 1"
    )
