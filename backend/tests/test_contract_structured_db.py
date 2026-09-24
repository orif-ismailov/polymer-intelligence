"""A contract's terms as data, not only as text (real Postgres).

Price, quantity and terms used to live only as strings inside `contracts.variables`
and in the PDF. The market analytics to come reads them as numbers, so they are
written as columns and `contract_lines` on every create and edit — for both rails —
and every Didox document keeps its own lines as it went to the operator.
"""

from __future__ import annotations

import datetime
import decimal
import hashlib

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

_VARS = {
    "product": "Полиэтилен HDPE",
    "qty": "20",
    "unit": "t",
    "price": "1 150,50",
    "currency": "USD",
    "incoterms": "FCA",
    "payment_terms": "100% предоплата",
    "delivery_window": "10 дней",
}


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _patch(monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import render as contract_render  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    monkeypatch.setattr(storage_service, "get_object_text", lambda path: "<p>{{ title }}</p>")
    monkeypatch.setattr(contract_render, "render_contract_pdf", lambda *a, **k: b"%PDF-fake")
    monkeypatch.setattr(
        storage_service, "store_contract_pdf",
        lambda pid, n, pdf: (f"contracts/{pid}/v{n}.pdf", hashlib.sha256(pdf).hexdigest()),
    )


def _parties(db):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.contracts.models import ContractTemplate  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    acc_a = make_account(db, "+998900000001")
    comp_a = company_service.create_company(db, acc_a, "UZ", "301111111")
    acc_b = make_account(db, "+998900000002")
    comp_b = company_service.create_company(db, acc_b, "UZ", "302222222")
    for company in (comp_a, comp_b):
        company.status = CompanyStatus.verified
    tpl = ContractTemplate(
        code="SUPPLY_TEST", name_ru="Договор", body_storage_path="x",
        variables_schema={"type": "object"}, version=1,
    )
    db.add(tpl)
    db.flush()
    return acc_a, comp_a, comp_b, tpl


def _lines(db, contract_id: int):  # noqa: ANN001, ANN202
    from app.domains.contracts.models import ContractLine  # noqa: PLC0415

    return (
        db.query(ContractLine)
        .filter(ContractLine.contract_id == contract_id)
        .order_by(ContractLine.ord_no)
        .all()
    )


@requires_real_db
def test_creating_a_contract_records_its_terms_as_columns_and_a_line(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        acc, comp_a, comp_b, tpl = _parties(db)
        contract = contract_service.create_contract(db, comp_a, acc, tpl, dict(_VARS), comp_b)
        db.commit()

        assert (contract.currency, contract.incoterms) == ("USD", "FCA")
        assert contract.payment_terms == "100% предоплата"
        assert contract.delivery_window == "10 дней"
        assert contract.amount_total == D("23010.00")
        [line] = _lines(db, contract.id)
        assert (line.ord_no, line.product_name, line.unit, line.currency) == (
            1, "Полиэтилен HDPE", "t", "USD"
        )
        assert (line.qty, line.price, line.amount) == (D("20"), D("1150.5"), D("23010.00"))


@requires_real_db
def test_editing_the_terms_rewrites_them(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        acc, comp_a, comp_b, tpl = _parties(db)
        contract = contract_service.create_contract(db, comp_a, acc, tpl, dict(_VARS), comp_b)
        contract_service.update_variables(
            db, contract, acc, {**_VARS, "qty": "5", "currency": "UZS"}, tpl
        )
        db.commit()

        assert contract.currency == "UZS"
        [line] = _lines(db, contract.id)
        assert (line.qty, line.currency, line.amount) == (D("5"), "UZS", D("5752.50"))


@requires_real_db
def test_a_price_that_is_not_a_number_is_recorded_as_unknown(sf, monkeypatch) -> None:  # noqa: ANN001
    """Zero would be a price nobody agreed to — and it would drag every average."""
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        acc, comp_a, comp_b, tpl = _parties(db)
        contract = contract_service.create_contract(
            db, comp_a, acc, tpl, {**_VARS, "price": "договорная"}, comp_b
        )
        db.commit()

        [line] = _lines(db, contract.id)
        assert line.price is None
        assert line.amount is None
        assert contract.amount_total is None


@requires_real_db
def test_a_didox_document_keeps_its_lines(sf, monkeypatch) -> None:  # noqa: ANN001
    """What went to the operator, as numbers — written before the provider call."""
    from app.domains.edi import onboarding  # noqa: PLC0415
    from app.domains.edi import service as edi_service  # noqa: PLC0415
    from app.domains.edi.models import DidoxDocumentLine  # noqa: PLC0415
    from app.domains.edi.payloads import DocumentLine  # noqa: PLC0415
    from app.integrations.didox import DidoxError  # noqa: PLC0415

    monkeypatch.setattr(onboarding, "_is_live", lambda: True)

    class _Refusing:
        def create_document(self, doc_type, payload, **_):  # noqa: ANN001, ANN202
            raise DidoxError(422, "refused")

    line = DocumentLine(
        ord_no=1, name="HDPE", catalog_code="03901001001000000", catalog_name="Полиэтилен",
        package_code="1486991", package_name="тонна", count=D("2.5"), price=D("1000.00"),
        vat_rate=12, origin=1,
    )
    with sf() as db:
        acc, comp_a, comp_b, _tpl = _parties(db)
        with pytest.raises(DidoxError):
            edi_service.create_document(
                db, doc_type="002", subject_kind="contract", subject_id=1,
                owner_company_id=comp_a.id, partner_company_id=comp_b.id, deal_id=None,
                number="ЭСФ-2026-000001", doc_date=datetime.date(2026, 9, 24),
                payload={}, created_by_user_account_id=acc.id, user_key="k",
                tax_id=comp_a.tax_id, client=_Refusing(), lines=[line],
            )
        db.commit()

        [stored] = db.query(DidoxDocumentLine).all()
        assert (stored.ikpu_code, stored.package_code, stored.origin) == (
            "03901001001000000", "1486991", 1
        )
        assert (stored.qty, stored.price, stored.vat_rate) == (D("2.5"), D("1000.00"), 12)
        assert (stored.amount, stored.vat_sum) == (D("2500.00"), D("300.00"))


_MGBUS_ONE_OFF = {
    "contract_kind": "one_off", "contract_number": "297-08", "contract_date": "15.08.2024",
    "product": "МЭГ", "qty": "120000", "unit": "kg", "unit_price": "16300", "vat_rate": "12",
    "payment_mode": "prepay", "delivery_days": "5", "delivery_basis": "supplier_warehouse",
}


@requires_real_db
def test_a_one_off_contract_priced_with_vat_is_stored_without_it(sf, monkeypatch) -> None:  # noqa: ANN001
    """The unit price analytics compares is the price without VAT; the contract
    total is what the parties signed — with it."""
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        acc, comp_a, comp_b, tpl = _parties(db)
        contract = contract_service.create_contract(db, comp_a, acc, tpl, dict(_MGBUS_ONE_OFF), comp_b)
        db.commit()

        assert contract.amount_total == D("1956000000.00")
        assert contract.currency == "UZS"
        assert (contract.payment_terms, contract.incoterms, contract.delivery_window) == (
            "prepay", "supplier_warehouse", "5"
        )
        [line] = _lines(db, contract.id)
        assert (line.price, line.amount, line.vat_rate) == (D("14553.57"), D("1746428571.43"), 12)


@requires_real_db
def test_a_frame_contract_keeps_its_limit_and_no_line(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        acc, comp_a, comp_b, tpl = _parties(db)
        contract = contract_service.create_contract(
            db, comp_a, acc, tpl,
            {"contract_kind": "frame", "goods_description": "Сырье", "amount_limit": "20000000000"},
            comp_b,
        )
        db.commit()

        assert contract.amount_total == D("20000000000.00")
        assert _lines(db, contract.id) == []
