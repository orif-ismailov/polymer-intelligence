"""The Didox card for a contract drawn up from a TENDER (real Postgres).

A tender contract has no offer, so the seller picks the ИКПУ on the card. What the
card is told decides whether anyone can ever sign: `ikpu_missing` there used to be
a dead end with no button on either side.
"""

from __future__ import annotations

import decimal
from typing import Any

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


class _Didox:
    """Knows every ИНН; the buyer has declared only `declared`."""

    def __init__(self, declared: set[str]) -> None:
        self.declared = declared
        self.asked: list[tuple[str, str]] = []

    def info_by_tin(self, tax_id: str) -> Any:  # noqa: ANN401
        return object()

    def class_packages(self, tax_id: str, class_code: str, **_: Any) -> list[tuple[str, str]]:
        from app.integrations.didox import DidoxError  # noqa: PLC0415

        self.asked.append((tax_id, class_code))
        if class_code not in self.declared:
            raise DidoxError(422, "танланган МХИКлар рўйхатида мавжуд эмас")
        return [("1486991", "тонна")]


def _tender_contract(db):  # noqa: ANN001, ANN202
    """Buyer's tender → seller's accepted quote → deal → Didox contract, no offer."""
    from app.domains.contracts.models import Contract, ContractTemplate  # noqa: PLC0415
    from app.domains.deals import service as deal_service  # noqa: PLC0415
    from app.domains.deals.models import RfqResponse  # noqa: PLC0415
    from app.models.enums import CompanyStatus, ContractStatus  # noqa: PLC0415

    buyer_acc = make_account(db, "+998900000001")
    buyer = make_company(db, buyer_acc, tax_id="301111111")
    seller_acc = make_account(db, "+998900000002")
    seller = make_company(db, seller_acc, tax_id="302222222")
    for company in (buyer, seller):
        company.status = CompanyStatus.verified
    request = make_request(db, company=buyer, account=buyer_acc)
    response = RfqResponse(
        request_id=request.id, company_id=seller.id, created_by_user_account_id=seller_acc.id,
        price=decimal.Decimal("1250.00"), currency="USD", qty=decimal.Decimal("10"), qty_unit="MT",
    )
    db.add(response)
    db.flush()
    deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
    template = ContractTemplate(
        code="SUPPLY_TEST", name_ru="Договор", body_storage_path="x",
        variables_schema={"type": "object"}, version=1,
    )
    db.add(template)
    db.flush()
    contract = Contract(
        template_id=template.id, template_version=1,
        initiator_company_id=seller.id, counterparty_company_id=buyer.id,
        title="Supply", created_by_user_account_id=seller_acc.id,
        variables={"product": "Полипропилен (PP)", "qty": "10", "price": "1250.00"},
        signing_provider="didox", status=ContractStatus.pending_signatures,
    )
    db.add(contract)
    db.flush()
    deal.contract_id = contract.id
    db.flush()
    return contract, seller, buyer


@requires_real_db
def test_a_tender_contract_asks_the_seller_for_the_code(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.edi import api_portal  # noqa: PLC0415

    monkeypatch.setattr(api_portal, "get_didox_client", lambda: _Didox(set()))
    with sf() as db:
        contract, seller, _buyer = _tender_contract(db)
        out = api_portal._prefill(db, contract, seller.id)  # noqa: SLF001

    assert out.ikpu_choice is True
    assert not any(code.startswith("ikpu_missing") for code in out.blockers), (
        "there is no объявление to fix — the card asks for the code instead"
    )
    # The seller still confirms the contract's own terms.
    [line] = out.lines
    assert (line.name, line.count, line.price) == (
        "Полипропилен (PP)", decimal.Decimal("10"), decimal.Decimal("1250.00")
    )


@requires_real_db
def test_the_chosen_code_is_checked_against_the_buyers_list(sf, monkeypatch) -> None:  # noqa: ANN001
    """Didox refuses a code the BUYER has not declared — at `/sign`, after the
    seller has typed a key password. The card says so first."""
    from app.domains.edi import api_portal  # noqa: PLC0415

    didox = _Didox({"03902001001000000"})
    monkeypatch.setattr(api_portal, "get_didox_client", lambda: didox)
    with sf() as db:
        contract, seller, buyer = _tender_contract(db)
        declared = api_portal._prefill(  # noqa: SLF001
            db, contract, seller.id, ikpu_code="03902001001000000"
        )
        undeclared = api_portal._prefill(  # noqa: SLF001
            db, contract, seller.id, ikpu_code="03901001001000000"
        )

    assert "counterparty_ikpu_missing" not in declared.blockers
    assert "counterparty_ikpu_missing" in undeclared.blockers
    assert ("301111111", "03901001001000000") in didox.asked
