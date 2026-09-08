"""Reference-number sequences vs. rows the seeders wrote by hand (real Postgres).

The regression: `seed_showcase` INSERTs `DEAL-2026-000001` … as literals and
`purge()` DROPs `deal_seq_2026`, so numbering "restarts with the data" — on top
of it. The first REAL deal after a seed drew `nextval` = 1, rebuilt
`DEAL-2026-000001`, and died on `uq_deals_number`. The user-visible failure was a
**500 on accepting a supplier's quote**: the tender stayed open, no deal was
created, and the deal room / contract / signing chain behind it was unreachable.

None of this can be checked against a stub. `nextval`, `setval`, `pg_sequences`
and a UNIQUE violation are the whole subject, and the collision only exists
because the sequence and the row disagree in a real database.
"""

from __future__ import annotations

import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)


def _seed_deal_by_hand(db, buyer, seller, account, number: str) -> None:  # noqa: ANN001
    """Insert a deal the way the showcase seeders do — number as a literal."""
    db.execute(
        sa.text(
            """
            INSERT INTO deals (number, buyer_company_id, seller_company_id, status,
                               amount, currency, created_by_user_account_id)
            VALUES (:number, :buyer, :seller, 'negotiation', 1000, 'USD', :account)
            """
        ),
        {"number": number, "buyer": buyer, "seller": seller, "account": account},
    )


@requires_real_db
def test_a_hand_written_number_collides_until_the_sequence_is_aligned() -> None:
    """Both halves in one test: the failure, then the fix.

    Asserting only the fix would let someone delete `align_reference_numbers` and
    still pass, because a clean database never reproduces this.
    """
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.seed.align_numbering import align_reference_numbers  # noqa: PLC0415

    engine = make_engine()
    migrate_head()
    clean(engine)
    session = session_factory(engine)

    with session() as db:
        buyer_account = make_account(db, "+998900000001")
        seller_account = make_account(db, "+998900000002")
        buyer = make_company(db, buyer_account, "301111111")
        seller = make_company(db, seller_account, "302222222")
        db.flush()

        year = deal_service.generate_deal_number(db).split("-")[1]
        # generate_deal_number just consumed 1; start from a clean sequence so the
        # seeded rows are the only thing occupying the low numbers.
        db.execute(sa.text(f"DROP SEQUENCE IF EXISTS deal_seq_{year}"))
        for n in (1, 2, 3):
            _seed_deal_by_hand(
                db, buyer.id, seller.id, buyer_account.id, f"DEAL-{year}-{n:06d}"
            )
        db.flush()

        # THE BUG: nothing told the sequence, so it hands out a taken number.
        assert deal_service.generate_deal_number(db) == f"DEAL-{year}-000001"
        db.execute(sa.text(f"DROP SEQUENCE IF EXISTS deal_seq_{year}"))

        # THE FIX.
        moved = align_reference_numbers(db)
        assert moved[f"deal_seq_{year}"] == 3
        assert deal_service.generate_deal_number(db) == f"DEAL-{year}-000004"

        # Monotonic: a second alignment must not rewind what has been drawn.
        align_reference_numbers(db)
        assert deal_service.generate_deal_number(db) == f"DEAL-{year}-000005"

        db.rollback()

    clean(engine)


@requires_real_db
def test_requests_align_per_day_not_per_year() -> None:
    """`REQ-` is numbered per DAY (`req_seq_YYYYMMDD`), unlike every other family.

    A single yearly max would leave every other seeded day unaligned — and
    `seed_showcase.purge()` drops `request_seq_{year}`, a name nothing generates,
    so that half was never even reaching the right sequence.
    """
    from app.domains.requests import service as request_service  # noqa: PLC0415
    from app.seed.align_numbering import align_reference_numbers  # noqa: PLC0415

    engine = make_engine()
    migrate_head()
    clean(engine)
    session = session_factory(engine)

    with session() as db:
        account = make_account(db, "+998900000001")
        company = make_company(db, account, "301111111")
        db.flush()

        today = request_service.generate_request_number(db)  # REQ-YYYY-MM-DD-00001
        _, yyyy, mm, dd, _ = today.split("-")
        db.execute(sa.text(f"DROP SEQUENCE IF EXISTS req_seq_{yyyy}{mm}{dd}"))

        for n in (1, 2):
            db.execute(
                sa.text(
                    """
                    INSERT INTO requests (number, company_id, created_by_user_account_id,
                                          product_text, volume)
                    VALUES (:number, :company, :account, 'HDPE film', 10)
                    """
                ),
                {
                    "number": f"REQ-{yyyy}-{mm}-{dd}-{n:05d}",
                    "company": company.id,
                    "account": account.id,
                },
            )
        # A different day must get its own sequence, untouched by today's.
        db.execute(
            sa.text(
                """
                INSERT INTO requests (number, company_id, created_by_user_account_id,
                                      product_text, volume)
                VALUES (:number, :company, :account, 'PP raffia', 10)
                """
            ),
            {
                "number": f"REQ-{yyyy}-01-02-00042",
                "company": company.id,
                "account": account.id,
            },
        )
        db.flush()

        moved = align_reference_numbers(db)
        assert moved[f"req_seq_{yyyy}{mm}{dd}"] == 2
        assert moved[f"req_seq_{yyyy}0102"] == 42
        assert request_service.generate_request_number(db) == f"REQ-{yyyy}-{mm}-{dd}-00003"

        db.rollback()

    clean(engine)


def test_the_migration_and_the_seeder_share_one_table_map() -> None:
    """DB-free. Two copies of the same list is how one of them goes stale.

    The migration repairs already-seeded deployments and the seeder keeps new
    ones right; a family present in one and missing from the other is a silent
    half-fix.
    """
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from app.seed.align_numbering import _YEARLY as SEEDER_MAP  # noqa: N811, PLC0415

    path = (
        Path(__file__).parent.parent
        / "alembic" / "versions" / "0049_align_reference_sequences.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_0049", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert set(module._YEARLY) == set(SEEDER_MAP)
