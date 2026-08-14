"""Real-Postgres tests for the escrow outbox consumer (P3 W1 — T1.4).

Guarded (localhost test_polymer). The consumer is what makes the demo line true
without anyone calling escrow: two parties sign a contract, and the deal is
already `payment_pending` with an invoice against it.

Outbox delivery is at-least-once, so re-delivery is the normal case, not an edge
one — and every consumer here must be a no-op the second time.
"""

from __future__ import annotations

import decimal
from unittest.mock import patch

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


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _verified(db, tax, phone):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax)
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _signed_deal(db, *, amount=decimal.Decimal("25000.00")):  # noqa: ANN001, ANN202
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import RfqResponse  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415

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
    )
    db.add(response)
    db.flush()
    deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
    deal.amount = amount
    db.flush()
    deal_service.transition(
        db, deal, DealStatus.contract_pending, actor_kind=DealActorKind.system
    )
    deal_service.transition(
        db, deal, DealStatus.contract_signed, actor_kind=DealActorKind.system
    )
    return deal


def _fire(deal_id: int, to_status: str = "contract_signed") -> dict:
    """Run the consumer the way the dispatcher would, against the test DB."""
    from app.tasks.payments import open_escrow_on_deal_signed  # noqa: PLC0415

    with patch("app.core.db.engine", make_engine()):
        return open_escrow_on_deal_signed(
            event_id=None, aggregate_id=str(deal_id), payload={"to": to_status}
        )


@requires_real_db
def test_signing_a_contract_raises_the_escrow_by_itself(sf) -> None:  # noqa: ANN001
    """The DoD line: nobody calls escrow — the deal reaches payment_pending with
    a pending payment against it because the status event fired."""
    from app.domains.deals.models import Deal  # noqa: PLC0415
    from app.domains.deals.payment_models import EscrowPayment  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415

    with sf() as db:
        deal = _signed_deal(db)
        db.commit()
        deal_id = deal.id

    result = _fire(deal_id)
    assert result["status"] == "ok"

    with sf() as db:
        assert db.get(Deal, deal_id).status == DealStatus.payment_pending
        payment = db.query(EscrowPayment).filter(EscrowPayment.deal_id == deal_id).one()
        assert payment.status == EscrowStatus.pending
        assert payment.amount == decimal.Decimal("25000.00")


@requires_real_db
def test_redelivery_does_not_open_a_second_escrow(sf) -> None:  # noqa: ANN001
    from app.domains.deals.payment_models import EscrowPayment  # noqa: PLC0415

    with sf() as db:
        deal = _signed_deal(db)
        db.commit()
        deal_id = deal.id

    _fire(deal_id)
    replay = _fire(deal_id)

    with sf() as db:
        assert db.query(EscrowPayment).filter(EscrowPayment.deal_id == deal_id).count() == 1
    assert replay["status"] in {"ok", "noop"}


@requires_real_db
def test_other_status_changes_are_ignored(sf) -> None:  # noqa: ANN001
    """Every transition emits DEAL_STATUS_CHANGED and the dispatcher routes by
    type alone, so the consumer filters on the payload — anything but
    contract_signed must not raise an invoice."""
    from app.domains.deals.payment_models import EscrowPayment  # noqa: PLC0415

    with sf() as db:
        deal = _signed_deal(db)
        db.commit()
        deal_id = deal.id

    result = _fire(deal_id, to_status="contract_pending")
    assert result["status"] == "skipped"

    with sf() as db:
        assert db.query(EscrowPayment).count() == 0


@requires_real_db
def test_a_deal_with_no_amount_is_reported_not_crashed(sf) -> None:  # noqa: ANN001
    """A consumer that raises keeps its event unpublished and has the dispatcher
    retry it forever. This one records the blockage and returns."""
    from app.domains.deals.models import Deal  # noqa: PLC0415
    from app.domains.deals.payment_models import EscrowPayment  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415

    with sf() as db:
        deal = _signed_deal(db, amount=None)
        db.commit()
        deal_id = deal.id

    result = _fire(deal_id)
    assert result["status"] == "blocked"
    assert "amount" in str(result.get("reason", "")).lower()

    with sf() as db:
        assert db.query(EscrowPayment).count() == 0
        assert db.get(Deal, deal_id).status == DealStatus.contract_signed


@requires_real_db
def test_a_missing_deal_is_skipped(sf) -> None:  # noqa: ANN001
    assert _fire(999999)["status"] == "skipped"


@requires_real_db
def test_a_broken_payload_never_raises(sf) -> None:  # noqa: ANN001
    """A bad aggregate id must not wedge the outbox."""
    from app.tasks.payments import open_escrow_on_deal_signed  # noqa: PLC0415

    with patch("app.core.db.engine", make_engine()):
        assert (
            open_escrow_on_deal_signed(
                aggregate_id="not-a-number", payload={"to": "contract_signed"}
            )["status"]
            == "skipped"
        )
        assert (
            open_escrow_on_deal_signed(aggregate_id=None, payload={"to": "contract_signed"})[
                "status"
            ]
            == "skipped"
        )
        assert open_escrow_on_deal_signed(aggregate_id="1", payload=None)["status"] == "skipped"
