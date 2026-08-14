"""Real-Postgres tests for the contracts↔deals seam (P2 W1 — T1.4).

Guarded (localhost test_polymer). The deals context reacts to `CONTRACT_*`
domain events; the contracts context is untouched. What has to hold:

  * the link is single-sided and one-to-one (`deals.contract_id`),
  * signing a contract advances its deal WITHOUT anyone calling deal_service,
  * every consumer is idempotent, because outbox delivery is at-least-once,
  * a contract with no deal is a no-op, not a crash.
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
    company.legal_name = f"OOO {tax}"
    db.flush()
    return account, company


def _deal_with_contract(db):  # noqa: ANN001, ANN202
    """A deal in negotiation with a draft contract attached."""
    from app.domains.contracts.models import Contract, ContractTemplate  # noqa: PLC0415
    from app.models.deals import RfqResponse  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

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

    template = ContractTemplate(
        code="SUPPLY_TEST",
        name_ru="Договор",
        body_storage_path="contracts/templates/x.html",
        variables_schema={"type": "object", "required": []},
        version=1,
    )
    db.add(template)
    db.flush()
    contract = Contract(
        template_id=template.id,
        template_version=1,
        initiator_company_id=buyer.id,
        counterparty_company_id=seller.id,
        title="Supply",
        variables={},
        created_by_user_account_id=buyer_acc.id,
    )
    db.add(contract)
    db.flush()
    deal_service.attach_contract(db, deal, contract, buyer_acc)
    return deal, contract, buyer_acc, buyer, seller_acc, seller


# ── Linking ───────────────────────────────────────────────────────────────────


@requires_real_db
def test_attach_links_the_deal_to_the_contract(sf) -> None:  # noqa: ANN001
    with sf() as db:
        deal, contract, *_ = _deal_with_contract(db)
        assert deal.contract_id == contract.id


@requires_real_db
def test_a_contract_cannot_serve_two_deals(sf) -> None:  # noqa: ANN001
    """The partial unique index is what lets the consumer look a deal up by
    contract_id and be sure of the answer."""
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

    with sf() as db:
        _deal, contract, buyer_acc, buyer, seller_acc, seller = _deal_with_contract(db)
        offer = SellerOffer(company_id=seller.id, product_text="HDPE")
        db.add(offer)
        db.flush()
        second = deal_service._open(
            db, buyer=buyer, seller=seller, account=buyer_acc, offer_id=offer.id
        )
        with pytest.raises(deal_service.DealAlreadyOpen):
            deal_service.attach_contract(db, second, contract, buyer_acc)


@requires_real_db
def test_attach_refuses_a_contract_between_other_companies(sf) -> None:  # noqa: ANN001
    from app.domains.contracts.models import Contract  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

    with sf() as db:
        deal, contract, buyer_acc, buyer, _sa, _s = _deal_with_contract(db)
        _other_acc, other = _verified(db, "303333333", "+998900000003")
        stranger = Contract(
            template_id=contract.template_id,
            template_version=1,
            initiator_company_id=buyer.id,
            counterparty_company_id=other.id,        # not the deal's seller
            title="Elsewhere",
            variables={},
            created_by_user_account_id=buyer_acc.id,
        )
        db.add(stranger)
        db.flush()
        deal.contract_id = None
        db.flush()
        with pytest.raises(deal_service.NotDealParticipant):
            deal_service.attach_contract(db, deal, stranger, buyer_acc)


@requires_real_db
def test_attach_is_idempotent_for_the_same_contract(sf) -> None:  # noqa: ANN001
    from app.services import deal_service  # noqa: PLC0415

    with sf() as db:
        deal, contract, buyer_acc, *_ = _deal_with_contract(db)
        deal_service.attach_contract(db, deal, contract, buyer_acc)
        assert deal.contract_id == contract.id


# ── Event-driven transitions ──────────────────────────────────────────────────


def _fire(task, contract_id: int) -> dict:  # noqa: ANN001
    """Run a consumer the way the dispatcher would, against the test DB."""
    with patch("app.core.db.engine", make_engine()):
        return task(event_id=None, aggregate_id=str(contract_id), payload={})


@requires_real_db
def test_sending_a_contract_moves_the_deal_to_contract_pending(sf) -> None:  # noqa: ANN001
    from app.models.deals import Deal  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.tasks.deals import advance_deal_on_contract_sent  # noqa: PLC0415

    with sf() as db:
        deal, contract, *_ = _deal_with_contract(db)
        db.commit()
        deal_id, contract_id = deal.id, contract.id

    _fire(advance_deal_on_contract_sent, contract_id)

    with sf() as db:
        assert db.get(Deal, deal_id).status == DealStatus.contract_pending


@requires_real_db
def test_both_signatures_advance_the_deal_without_anyone_calling_it(sf) -> None:  # noqa: ANN001
    """The DoD line: two parties sign, the deal reaches contract_signed by event."""
    from app.models.deals import Deal  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.tasks.deals import (  # noqa: PLC0415
        advance_deal_on_contract_activated,
        advance_deal_on_contract_sent,
    )

    with sf() as db:
        deal, contract, *_ = _deal_with_contract(db)
        db.commit()
        deal_id, contract_id = deal.id, contract.id

    _fire(advance_deal_on_contract_sent, contract_id)
    _fire(advance_deal_on_contract_activated, contract_id)

    with sf() as db:
        assert db.get(Deal, deal_id).status == DealStatus.contract_signed


@requires_real_db
def test_redelivery_does_not_transition_twice(sf) -> None:  # noqa: ANN001
    """Outbox delivery is at-least-once; a replayed activation must be a no-op."""
    from app.models.deals import Deal, DealStatusHistory  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.tasks.deals import (  # noqa: PLC0415
        advance_deal_on_contract_activated,
        advance_deal_on_contract_sent,
    )

    with sf() as db:
        deal, contract, *_ = _deal_with_contract(db)
        db.commit()
        deal_id, contract_id = deal.id, contract.id

    _fire(advance_deal_on_contract_sent, contract_id)
    _fire(advance_deal_on_contract_activated, contract_id)
    replay = _fire(advance_deal_on_contract_activated, contract_id)

    assert replay["status"] in {"skipped", "noop"}
    with sf() as db:
        assert db.get(Deal, deal_id).status == DealStatus.contract_signed
        signed = (
            db.query(DealStatusHistory)
            .filter(
                DealStatusHistory.deal_id == deal_id,
                DealStatusHistory.to_status == DealStatus.contract_signed,
            )
            .count()
        )
        assert signed == 1, "a replayed event must not duplicate the timeline row"


@requires_real_db
def test_declining_a_contract_returns_the_deal_to_negotiation(sf) -> None:  # noqa: ANN001
    from app.models.deals import Deal  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.tasks.deals import (  # noqa: PLC0415
        advance_deal_on_contract_sent,
        roll_back_deal_on_contract_closed,
    )

    with sf() as db:
        deal, contract, *_ = _deal_with_contract(db)
        db.commit()
        deal_id, contract_id = deal.id, contract.id

    _fire(advance_deal_on_contract_sent, contract_id)
    _fire(roll_back_deal_on_contract_closed, contract_id)

    with sf() as db:
        # Back to negotiation and free to try another contract — a declined
        # draft must not kill the trade.
        assert db.get(Deal, deal_id).status == DealStatus.negotiation


@requires_real_db
def test_rollback_after_signature_is_ignored(sf) -> None:  # noqa: ANN001
    """A cancelled/expired event arriving late must not undo a signed deal."""
    from app.models.deals import Deal  # noqa: PLC0415
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.tasks.deals import (  # noqa: PLC0415
        advance_deal_on_contract_activated,
        advance_deal_on_contract_sent,
        roll_back_deal_on_contract_closed,
    )

    with sf() as db:
        deal, contract, *_ = _deal_with_contract(db)
        db.commit()
        deal_id, contract_id = deal.id, contract.id

    _fire(advance_deal_on_contract_sent, contract_id)
    _fire(advance_deal_on_contract_activated, contract_id)
    _fire(roll_back_deal_on_contract_closed, contract_id)

    with sf() as db:
        assert db.get(Deal, deal_id).status == DealStatus.contract_signed


@requires_real_db
def test_contract_without_a_deal_is_a_noop(sf) -> None:  # noqa: ANN001
    """Contracts created outside a deal (the R3 flow) still emit these events."""
    from app.tasks.deals import advance_deal_on_contract_activated  # noqa: PLC0415

    with sf() as db:
        deal, contract, buyer_acc, *_ = _deal_with_contract(db)
        deal.contract_id = None
        db.commit()
        contract_id = contract.id

    result = _fire(advance_deal_on_contract_activated, contract_id)
    assert result["status"] in {"skipped", "noop"}


# ── Prefill ───────────────────────────────────────────────────────────────────


@requires_real_db
def test_prefill_carries_the_agreed_terms(sf) -> None:  # noqa: ANN001
    from app.services import deal_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_with_contract(db)
        prefill = deal_service.contract_prefill(db, deal)
        assert prefill["price"] == "1250.00"
        assert prefill["currency"] == "USD"
        assert prefill["qty"] == "20"
        assert prefill["unit"] == "t", "MT is the RFQ unit; the template speaks kg/t/pcs"
        assert prefill["product"] == "HDPE film"


@requires_real_db
def test_prefill_drops_values_a_template_would_reject(sf) -> None:  # noqa: ANN001
    """FOB is a real Incoterm and a real PriceBasis, but SUPPLY_V1 does not list
    it. Prefilling it would fail validation and block the entire form."""
    from app.models.deals import RfqResponse  # noqa: PLC0415
    from app.models.enums import PriceBasis  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

    with sf() as db:
        deal, *_ = _deal_with_contract(db)
        response = (
            db.query(RfqResponse).filter(RfqResponse.deal_id == deal.id).one()
        )
        response.incoterms = PriceBasis.FOB
        db.flush()

        schema = {
            "type": "object",
            "properties": {"incoterms": {"enum": ["EXW", "FCA", "CPT", "DAP", "DDP"]}},
        }
        assert "incoterms" not in deal_service.contract_prefill(db, deal, schema=schema)
        # Without a schema the raw domain value is offered as-is.
        assert deal_service.contract_prefill(db, deal)["incoterms"] == "FOB"
