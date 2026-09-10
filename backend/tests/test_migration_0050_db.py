"""Real-Postgres tests for migration 0050 — the IMEX-6 backfill.

Guarded (localhost `test_polymer`). The pre-fix state cannot be produced through
the services any more (that is the point of the fix), so each test writes it the
way the old code left it: an accepted quote and a deal, with the request still
reading `new` and its timeline holding only the creation row.

What is actually at risk in a data migration is its WHERE clause, so that is what
these cover — which rows it repairs, which it must leave alone, and what happens
when it runs twice.
"""

from __future__ import annotations

import decimal
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_request,
    migrate_head,
    requires_real_db,
    session_factory,
)

BACKEND_DIR = Path(__file__).parent.parent
_MIGRATION = BACKEND_DIR / "alembic" / "versions" / "0050_backfill_matched_tenders.py"


def _load_migration():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("migration_0050", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    return session_factory(engine)


def _verified(db, tax, phone, **kw):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax, **kw)
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _pre_fix_tender(db, *, status: str = "new"):  # noqa: ANN001, ANN202
    """The state the OLD accept path left behind: deal opened, tender untouched.

    Written directly rather than through `open_deal_from_response`, which now
    transitions the request — the bug is no longer reachable through the service.
    """
    from app.domains.deals.models import Deal, RfqResponse  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        DealStatus,
        RequestStatus,
        RfqResponseStatus,
    )

    buyer_acc, buyer = _verified(db, "301111111", "+998900000001")
    seller_acc, seller = _verified(db, "302222222", "+998900000002")

    request = make_request(db, company=buyer, account=buyer_acc)
    response = RfqResponse(
        request_id=request.id,
        company_id=seller.id,
        created_by_user_account_id=seller_acc.id,
        price=decimal.Decimal("1250.00"),
        currency="USD",
        qty=decimal.Decimal("20"),
        qty_unit="MT",
        status=RfqResponseStatus.accepted,
    )
    db.add(response)
    db.flush()

    deal = Deal(
        number=f"DEAL-2026-{request.id:06d}",
        buyer_company_id=buyer.id,
        seller_company_id=seller.id,
        request_id=request.id,
        status=DealStatus.negotiation,
        amount=decimal.Decimal("25000.00"),
        currency="USD",
        created_by_user_account_id=buyer_acc.id,
    )
    db.add(deal)

    request.status = RequestStatus(status)
    db.flush()
    # The reported symptom: a timeline holding only the creation row.
    db.execute(
        sa.text("DELETE FROM request_status_history WHERE request_id = :rid"),
        {"rid": request.id},
    )
    db.flush()
    return request, response, deal


def _history(db, request_id: int) -> list[tuple]:
    return [
        (r[0], r[1], r[2])
        for r in db.execute(
            sa.text(
                "SELECT from_status::text, to_status::text, changed_by "
                "FROM request_status_history WHERE request_id = :rid ORDER BY id"
            ),
            {"rid": request_id},
        ).all()
    ]


@requires_real_db
def test_a_new_tender_with_a_deal_is_repaired(sf) -> None:  # noqa: ANN001
    """The QA row: `new` with an accepted quote and a live deal."""
    module = _load_migration()

    with sf() as db:
        request, response, deal = _pre_fix_tender(db)
        assert _history(db, request.id) == []

        repaired = module.backfill(db.connection())
        db.expire_all()

        assert repaired == 1
        assert db.execute(
            sa.text("SELECT status::text FROM requests WHERE id = :rid"),
            {"rid": request.id},
        ).scalar_one() == "matched"
        assert _history(db, request.id) == [
            ("new", "offer_sent", None),
            ("offer_sent", "matched", None),
        ], "the ladder, with changed_by NULL — the buyer is not staff"


@requires_real_db
def test_the_history_rows_carry_the_real_timestamps(sf) -> None:  # noqa: ANN001
    """Nothing is invented: `offer_sent` is the quote's time, `matched` the deal's."""
    module = _load_migration()

    with sf() as db:
        request, response, deal = _pre_fix_tender(db)
        quoted_at, dealt_at = response.created_at, deal.created_at

        module.backfill(db.connection())

        stamps = db.execute(
            sa.text(
                "SELECT to_status::text, created_at FROM request_status_history "
                "WHERE request_id = :rid ORDER BY id"
            ),
            {"rid": request.id},
        ).all()
        assert dict(stamps) == {"offer_sent": quoted_at, "matched": dealt_at}


@requires_real_db
def test_an_offer_sent_tender_gets_only_the_matched_row(sf) -> None:  # noqa: ANN001
    """It already passed through `offer_sent`; a second such row would be a lie."""
    module = _load_migration()

    with sf() as db:
        request, *_ = _pre_fix_tender(db, status="offer_sent")

        assert module.backfill(db.connection()) == 1
        assert _history(db, request.id) == [("offer_sent", "matched", None)]


@requires_real_db
@pytest.mark.parametrize("status", ["cancelled", "closed"])
def test_a_closed_tender_is_left_alone(sf, status: str) -> None:  # noqa: ANN001
    """Finding 1's residue, NOT a row to repair.

    A cancelled tender carrying an accepted quote and a deal is the old bug's
    output. Setting it `matched` would overwrite a cancellation somebody meant.
    """
    module = _load_migration()

    with sf() as db:
        request, *_ = _pre_fix_tender(db, status=status)

        assert module.backfill(db.connection()) == 0
        assert db.execute(
            sa.text("SELECT status::text FROM requests WHERE id = :rid"),
            {"rid": request.id},
        ).scalar_one() == status
        assert _history(db, request.id) == []


@requires_real_db
def test_a_tender_with_no_deal_is_left_alone(sf) -> None:  # noqa: ANN001
    """An open tender that nobody has won is simply an open tender."""
    from app.models.enums import RequestStatus  # noqa: PLC0415

    module = _load_migration()

    with sf() as db:
        buyer_acc, buyer = _verified(db, "301111111", "+998900000001")
        request = make_request(db, company=buyer, account=buyer_acc)

        assert module.backfill(db.connection()) == 0
        db.expire_all()
        assert request.status == RequestStatus.new


@requires_real_db
def test_running_twice_changes_nothing_the_second_time(sf) -> None:  # noqa: ANN001
    """Idempotent: the WHERE clause stops matching once the status is `matched`."""
    module = _load_migration()

    with sf() as db:
        request, *_ = _pre_fix_tender(db)

        assert module.backfill(db.connection()) == 1
        after_first = _history(db, request.id)

        assert module.backfill(db.connection()) == 0
        assert _history(db, request.id) == after_first


class TestRevision:
    def test_migration_is_wired_into_the_chain(self) -> None:
        module = _load_migration()
        assert module.revision == "0050"
        assert module.down_revision == "0049"

    def test_open_statuses_match_the_state_machine(self) -> None:
        """The migration's `_OPEN` must be exactly the statuses the live machine
        still allows `matched` from — a second, drifting copy of that rule is how
        a backfill silently starts repairing (or skipping) the wrong rows.
        """
        from app.domains.requests.service import VALID_TRANSITIONS  # noqa: PLC0415
        from app.models.enums import RequestStatus  # noqa: PLC0415

        module = _load_migration()
        from_machine = {
            status.value
            for status, allowed in VALID_TRANSITIONS.items()
            if RequestStatus.matched in allowed
        }
        assert set(module._OPEN) == from_machine
