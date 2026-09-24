"""Issuing an ЭСФ (Didox 002) against a signed contract (real Postgres).

The builder existed since P7.a and nothing called it. The rules here decide
whether the invoice is one the roaming centre accepts:

  * only a SIGNED contract, and only its SELLER, issues one;
  * the ЭСФ quotes the договор's number and date EXACTLY — off the stored 007 on
    the Didox rail, or the contract's own number and activation date on E-IMZO;
  * goods ship in parts, so a contract may carry several invoices, and what is
    left to invoice is the contract's quantity less the invoices still standing;
  * one unsigned draft at a time — a second press must not mint a second number;
  * ЭСФ are in soum: a contract priced in another currency gets no price prefill.
"""

from __future__ import annotations

import datetime
import decimal
import itertools
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

D = decimal.Decimal
_TODAY = datetime.date(2026, 9, 24)
_IKPU = SimpleNamespace(
    ikpu_code="03901001001000000",
    ikpu_name="Полиэтилен",
    ikpu_package_code="1486991",
    ikpu_package_name="тонна",
    ikpu_origin=2,
)


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from app.domains.edi import onboarding  # noqa: PLC0415

    monkeypatch.setattr(onboarding, "_is_live", lambda: True)
    clean(engine)
    yield session_factory(engine)
    clean(engine)


class _Didox:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict]] = []
        self._ids = itertools.count(1)

    def create_document(self, doc_type, payload, **_):  # noqa: ANN001, ANN202
        self.created.append((doc_type, payload))
        n = next(self._ids)
        return SimpleNamespace(didox_id=f"hex{n}", didox_contract_id=None)

    def vat_reg_status(self, tax_id, **_):  # noqa: ANN001, ANN202
        return None

    def info_by_tin(self, tin):  # noqa: ANN001, ANN202
        return SimpleNamespace(
            name=f"BUYER {tin}", director="PETROV PETR", director_pinfl="32345678901234",
            address="Ташкент", oked=None, bank_account=None, bank_mfo=None,
            vat_reg_code=None, vat_reg_status=None,
        )


def _contract(db, *, provider="eimzo", currency="UZS", qty="10", price="15000000"):  # noqa: ANN001, ANN202
    """An ACTIVE contract: seller = initiator (no deal, no offer)."""
    from app.core.crypto import encrypt_pii  # noqa: PLC0415
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.contracts import terms  # noqa: PLC0415
    from app.domains.contracts.eimzo_models import CompanyPersonData  # noqa: PLC0415
    from app.domains.contracts.models import Contract, ContractTemplate  # noqa: PLC0415
    from app.models.enums import CompanyStatus, ContractStatus  # noqa: PLC0415

    seller_acc = make_account(db, "+998900000001")
    seller = company_service.create_company(db, seller_acc, "UZ", "301111111")
    buyer_acc = make_account(db, "+998900000002")
    buyer = company_service.create_company(db, buyer_acc, "UZ", "302222222")
    for company in (seller, buyer):
        company.status = CompanyStatus.verified
        company.legal_name = f"OOO {company.tax_id}"
    db.add(CompanyPersonData(
        company_id=seller.id, full_name_enc=encrypt_pii("IVANOV IVAN"),
        pinfl_enc=encrypt_pii("31234567890123"), pinfl_last4="0123",
    ))
    template = ContractTemplate(
        code="SUPPLY_TEST", name_ru="Договор", body_storage_path="x",
        variables_schema={"type": "object"}, version=1,
    )
    db.add(template)
    db.flush()
    contract = Contract(
        template_id=template.id, template_version=1,
        initiator_company_id=seller.id, counterparty_company_id=buyer.id,
        title="Поставка", created_by_user_account_id=seller_acc.id,
        variables={"product": "HDPE", "qty": qty, "unit": "t", "price": price, "currency": currency},
        signing_provider=provider, status=ContractStatus.active,
        activated_at=datetime.datetime(2026, 9, 20, 21, 30, tzinfo=datetime.UTC),
    )
    db.add(contract)
    db.flush()
    terms.sync_structured(db, contract)
    return contract, seller, buyer, seller_acc


def _line(count: str, price: str = "15000000"):  # noqa: ANN202
    from app.domains.edi.payloads import line_from_offer  # noqa: PLC0415

    return line_from_offer(_IKPU, ord_no=1, name="HDPE", count=D(count), price=D(price))


def _issue(db, contract, seller, acc, didox, count="4"):  # noqa: ANN001, ANN202
    from app.domains.edi import facture_docs  # noqa: PLC0415

    return facture_docs.create_for_contract(
        db, contract, acting_company_id=seller.id, account_id=acc.id,
        lines=[_line(count)], user_key="k", client=didox, today=_TODAY,
    )


@requires_real_db
def test_an_unsigned_contract_is_not_invoiced(sf) -> None:  # noqa: ANN001
    from app.domains.edi import facture_docs  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415

    with sf() as db:
        contract, seller, _buyer, acc = _contract(db)
        contract.status = ContractStatus.pending_signatures
        with pytest.raises(facture_docs.ContractNotActive):
            _issue(db, contract, seller, acc, _Didox())


@requires_real_db
def test_only_the_seller_issues_it(sf) -> None:  # noqa: ANN001
    from app.domains.edi import contract_docs  # noqa: PLC0415

    with sf() as db:
        contract, _seller, buyer, acc = _contract(db)
        with pytest.raises(contract_docs.PartyMismatch):
            _issue(db, contract, buyer, acc, _Didox())


@requires_real_db
def test_an_eimzo_contract_is_quoted_by_its_own_number_and_signing_day(sf) -> None:  # noqa: ANN001
    with sf() as db:
        contract, seller, _buyer, acc = _contract(db)
        didox = _Didox()
        row = _issue(db, contract, seller, acc, didox)

    [(doc_type, payload)] = didox.created
    assert doc_type == "002"
    assert row.doc_type == "002"
    assert row.number.startswith("ЭСФ-2026-")
    # Activated at 21:30 UTC on the 20th — the 21st in Tashkent.
    assert payload["ContractDoc"] == {
        "ContractNo": f"C-{str(contract.public_id)[:8]}", "ContractDate": "2026-09-21",
    }
    assert "didoxcontractid" not in payload


@requires_real_db
def test_a_didox_contract_is_quoted_off_its_stored_007(sf) -> None:  # noqa: ANN001
    from app.domains.edi.models import DidoxDocument  # noqa: PLC0415

    with sf() as db:
        contract, seller, buyer, acc = _contract(db, provider="didox")
        db.add(DidoxDocument(
            doc_type="007", subject_kind="contract", subject_id=contract.id,
            owner_company_id=seller.id, partner_company_id=buyer.id, number="DEAL-2026-000007",
            doc_date=datetime.date(2026, 9, 18), status=3, payload={}, didox_id="c007",
            didox_contract_id="777", created_by_user_account_id=acc.id,
        ))
        db.flush()
        didox = _Didox()
        _issue(db, contract, seller, acc, didox)

    [(_, payload)] = didox.created
    assert payload["ContractDoc"] == {"ContractNo": "DEAL-2026-000007", "ContractDate": "2026-09-18"}
    assert payload["didoxcontractid"] == "777"


@requires_real_db
def test_one_unsigned_draft_at_a_time(sf) -> None:  # noqa: ANN001
    from app.domains.edi import facture_docs  # noqa: PLC0415

    with sf() as db:
        contract, seller, _buyer, acc = _contract(db)
        didox = _Didox()
        first = _issue(db, contract, seller, acc, didox)
        with pytest.raises(facture_docs.FacturePending) as exc:
            _issue(db, contract, seller, acc, didox)
        assert exc.value.document_id == first.id
        assert len(didox.created) == 1


@requires_real_db
def test_a_contract_is_invoiced_in_parts(sf) -> None:  # noqa: ANN001
    from app.domains.edi import facture_docs  # noqa: PLC0415
    from app.domains.edi.models import DidoxDocumentLine  # noqa: PLC0415

    with sf() as db:
        contract, seller, _buyer, acc = _contract(db, qty="10")
        didox = _Didox()
        first = _issue(db, contract, seller, acc, didox, count="4")
        first.status = 3  # signed by both — the next shipment may be invoiced
        db.flush()

        [suggested] = facture_docs.suggested_lines(db, contract)
        assert suggested.count == D("6")

        second = _issue(db, contract, seller, acc, didox, count="6")
        # The seller's own yearly sequence: the next number, whatever the first was
        # (a sequence outlives the rows a test deletes).
        assert int(second.number.rsplit("-", 1)[1]) == int(first.number.rsplit("-", 1)[1]) + 1
        stored = db.query(DidoxDocumentLine).filter(
            DidoxDocumentLine.didox_document_id == second.id
        ).one()
        assert (stored.qty, stored.ikpu_code, stored.origin) == (D("6"), "03901001001000000", 2)

        # A rejected invoice gives its quantity back.
        second.status = 4
        db.flush()
        [again] = facture_docs.suggested_lines(db, contract)
        assert again.count == D("6")


@requires_real_db
def test_a_contract_priced_in_dollars_gets_no_price_prefill(sf) -> None:  # noqa: ANN001
    """An ЭСФ is in soum. Copying 1150 USD into it would invoice 1150 сум."""
    from app.domains.edi import facture_docs  # noqa: PLC0415

    with sf() as db:
        contract, _seller, _buyer, _acc = _contract(db, currency="USD", price="1150")
        [line] = facture_docs.suggested_lines(db, contract)

    assert line.price is None
    assert line.count == D("10")


# ── the portal routes ─────────────────────────────────────────────────────────


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.domains.edi import api_portal as edi_api  # noqa: PLC0415
    from app.domains.edi import onboarding  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from tests._fake_redis import FakeRedis  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    didox = _Didox()
    monkeypatch.setattr(onboarding, "_is_live", lambda: True)
    monkeypatch.setattr(edi_api, "get_didox_client", lambda: didox)
    monkeypatch.setattr(edi_api, "_guard", lambda db: None)
    monkeypatch.setattr(edi_api, "_counterparty_blocker", lambda client, tin: None)
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    def _override_redis():  # noqa: ANN202
        yield fake_redis

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session, fake_redis, didox
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


@requires_real_db
def test_the_seller_reads_the_form_and_issues_an_invoice(api) -> None:  # noqa: ANN001
    client, session, fake_redis, didox = api
    with session() as db:
        contract, seller, _buyer, acc = _contract(db)
        db.commit()
        ids = (contract.id, seller.id, acc.id, seller.tax_id)
    contract_id, seller_id, acc_id, tax = ids
    url = f"/api/v1/portal/companies/{seller_id}/didox/contracts/{contract_id}/factures"

    form = client.get(url, headers=_auth(acc_id))
    assert form.status_code == 200, form.text
    out = form.json()
    assert (out["is_seller"], out["ikpu_choice"], out["blockers"]) == (True, True, [])
    assert out["lines"][0]["count"] == "10.000"

    fake_redis.set(f"didox:user_key:{tax}", "user-key")
    body = {
        "lines": [{"name": "HDPE", "count": "4", "price": "15000000", "vat_rate": 12}],
        "ikpu": {
            "code": "03901001001000000", "name": "Полиэтилен", "package_code": "1486991",
            "package_name": "тонна", "origin": 2,
        },
    }
    created = client.post(url, json=body, headers=_auth(acc_id))
    assert created.status_code == 201, created.text
    assert created.json()["doc_type"] == "002"

    again = client.post(url, json=body, headers=_auth(acc_id))
    assert again.status_code == 409
    assert again.json()["detail"] == {"error": "facture_pending", "document_id": created.json()["id"]}

    listed = client.get(url, headers=_auth(acc_id)).json()
    assert listed["pending_document_id"] == created.json()["id"]
    [doc] = listed["documents"]
    assert (doc["outgoing"], doc["total"]) == (True, "67200000.00")
    assert len(didox.created) == 1


@requires_real_db
def test_the_buyer_sees_the_invoice_but_no_form(api) -> None:  # noqa: ANN001
    client, session, _fake_redis, _didox = api
    with session() as db:
        contract, _seller, buyer, _acc = _contract(db)
        db.commit()
        buyer_acc = db.execute(
            sa.text("SELECT user_account_id FROM company_members WHERE company_id = :c"),
            {"c": buyer.id},
        ).scalar_one()
        ids = (contract.id, buyer.id, buyer_acc)
    contract_id, buyer_id, buyer_acc = ids

    form = client.get(
        f"/api/v1/portal/companies/{buyer_id}/didox/contracts/{contract_id}/factures",
        headers=_auth(buyer_acc),
    )
    assert form.status_code == 200
    assert form.json()["is_seller"] is False
    assert "not_seller" in form.json()["blockers"]


# ── a framework contract is invoiced by specification ─────────────────────────


def _frame_with_spec(db, monkeypatch, spec_status="active"):  # noqa: ANN001, ANN202
    import hashlib  # noqa: PLC0415

    from app.domains.contracts import render as contract_render  # noqa: PLC0415
    from app.domains.contracts import specifications  # noqa: PLC0415
    from app.domains.contracts.models import ContractTemplate  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    monkeypatch.setattr(storage_service, "get_object_text", lambda path: "<p>{{ spec_number }}</p>")
    monkeypatch.setattr(contract_render, "render_contract_pdf", lambda *a, **k: b"%PDF")
    monkeypatch.setattr(
        storage_service, "store_specification_pdf",
        lambda pid, n, pdf: (f"c/{pid}/s{n}.pdf", hashlib.sha256(pdf).hexdigest()),
    )
    contract, seller, buyer, acc = _contract(db)
    contract.variables = {"contract_kind": "frame", "contract_number": "346-01",
                          "contract_date": "15.01.2026", "amount_limit": "20000000000"}
    from app.domains.contracts import terms  # noqa: PLC0415

    terms.sync_structured(db, contract)
    db.add(ContractTemplate(code="SPECIFICATION_V1", kind="specification", name_ru="Спец",
                            body_storage_path="s", variables_schema={}, version=1))
    db.flush()
    spec = specifications.create_specification(
        db, contract, acc,
        {"lines": [{"product": "LL 0209AA", "qty": "120000", "unit": "kg", "unit_price": "14553.57"}],
         "price_basis": "without_vat", "vat_rate": "12"},
        today=_TODAY,
    )
    spec.status = spec_status
    db.flush()
    return contract, seller, acc, spec


@requires_real_db
def test_a_framework_contract_is_invoiced_by_its_specification(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.edi import facture_docs  # noqa: PLC0415
    from app.domains.edi.payloads import line_from_offer  # noqa: PLC0415

    with sf() as db:
        contract, seller, acc, spec = _frame_with_spec(db, monkeypatch)

        [suggested] = facture_docs.suggested_lines(db, contract, spec)
        assert (suggested.name, suggested.count, suggested.price) == ("LL 0209AA", D("120000"), D("14553.57"))

        # No specification named: a framework contract has nothing to invoice.
        assert facture_docs.suggested_lines(db, contract) == []
        with pytest.raises(facture_docs.SpecificationRequired):
            _issue(db, contract, seller, acc, _Didox())

        didox = _Didox()
        row = facture_docs.create_for_contract(
            db, contract, acting_company_id=seller.id, account_id=acc.id,
            lines=[line_from_offer(_IKPU, ord_no=1, name="LL 0209AA", count=D("50000"), price=D("14553.57"))],
            user_key="k", client=didox, today=_TODAY, specification=spec,
        )
        assert row.specification_id == spec.id
        [left] = facture_docs.suggested_lines(db, contract, spec)
        assert left.count == D("70000")
        # The ЭСФ quotes the contract the parties typed.
        [(_, payload)] = didox.created
        assert payload["ContractDoc"] == {"ContractNo": "346-01", "ContractDate": "2026-01-15"}


@requires_real_db
def test_an_unsigned_specification_is_not_invoiced(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.edi import facture_docs  # noqa: PLC0415

    with sf() as db:
        contract, seller, acc, spec = _frame_with_spec(db, monkeypatch, spec_status="pending_signatures")
        with pytest.raises(facture_docs.SpecificationRequired):
            facture_docs.create_for_contract(
                db, contract, acting_company_id=seller.id, account_id=acc.id,
                lines=[_line("1")], user_key="k", client=_Didox(), today=_TODAY, specification=spec,
            )
