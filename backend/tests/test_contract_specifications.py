"""Specifications of a framework contract — «Спецификация № N» (stage 2, 24.09.2026).

The pure half: lines and totals, pinned to the AKFA specification № 01; and the
service half against real Postgres: numbering, the framework-only rule, the goods
landing in `contract_lines`, and a PDF in the real specification's shape.
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

_AKFA_LINE = {"product": "Полиэтилен линейный в гранулах LL 0209AA", "qty": "120000", "unit": "kg",
              "unit_price": "16300"}


class TestLines:
    def test_the_akfa_specification(self) -> None:
        from app.domains.contracts import specifications

        lines = specifications.parse_lines({"lines": [_AKFA_LINE], "price_basis": "with_vat", "vat_rate": "12"})
        totals = specifications.totals(lines)
        assert totals.amount_with_vat == D("1956000000.00")
        assert totals.vat_sum == D("209571428.57")
        assert totals.amount_without_vat == D("1746428571.43")
        assert lines[0].vat.price_without_vat == D("14553.57")

    def test_several_lines_add_up(self) -> None:
        from app.domains.contracts import specifications

        lines = specifications.parse_lines(
            {
                "lines": [
                    {"product": "A", "qty": "10", "unit": "t", "unit_price": "100"},
                    {"product": "B", "qty": "2", "unit": "t", "unit_price": "50"},
                ],
                "price_basis": "without_vat",
                "vat_rate": "12",
            }
        )
        assert [line.ord_no for line in lines] == [1, 2]
        assert specifications.totals(lines).amount_with_vat == D("1232.00")

    def test_a_line_that_does_not_parse_is_named(self) -> None:
        from app.domains.contracts import specifications

        with pytest.raises(specifications.InvalidSpecification) as exc:
            specifications.parse_lines(
                {"lines": [_AKFA_LINE, {"product": "", "qty": "x", "unit": "kg", "unit_price": "1"}]}
            )
        assert exc.value.fields == ["lines.2.product", "lines.2.qty"]

    def test_no_lines_is_refused(self) -> None:
        from app.domains.contracts import specifications

        with pytest.raises(specifications.InvalidSpecification):
            specifications.parse_lines({"lines": []})

    def test_the_rows_are_escaped(self) -> None:
        from app.domains.contracts import specifications

        lines = specifications.parse_lines(
            {"lines": [{**_AKFA_LINE, "product": "<script>x</script>"}]}
        )
        html = specifications.render_values({}, lines)["spec_rows_html"]
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<td>кг</td>" in html


# ── the service ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from app.domains.contracts import render as contract_render  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    rendered: list[str] = []

    def fake_pdf(template_html, variables, initiator, counterparty, **_):  # noqa: ANN001, ANN202
        html = contract_render.render_contract_html(
            template_html, variables, initiator, counterparty, contract_public_id="x", generated_at="t"
        )
        rendered.append(html)
        return b"%PDF-spec"

    monkeypatch.setattr(storage_service, "get_object_text", lambda path: _SPEC_BODY)
    monkeypatch.setattr(contract_render, "render_contract_pdf", fake_pdf)
    monkeypatch.setattr(
        storage_service, "store_specification_pdf",
        lambda pid, n, pdf: (f"contracts/{pid}/specification_{n}.pdf", hashlib.sha256(pdf).hexdigest()),
    )
    clean(engine)
    yield session_factory(engine), rendered
    clean(engine)


_SPEC_BODY = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "app/seed/data/contract_templates/specification_mgbus_ru.html"
).read_text(encoding="utf-8")


def _frame(db, *, status="active", kind="frame"):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.contracts.models import Contract, ContractTemplate  # noqa: PLC0415
    from app.models.enums import CompanyStatus, ContractStatus  # noqa: PLC0415

    acc = make_account(db, "+998900000001")
    seller = company_service.create_company(db, acc, "UZ", "301111111")
    buyer_acc = make_account(db, "+998900000002")
    buyer = company_service.create_company(db, buyer_acc, "UZ", "302222222")
    for c, name in ((seller, "СП ООО «MGBUS»"), (buyer, "ООО «AKFA EXTRUSION»")):
        c.status = CompanyStatus.verified
        c.legal_name = name
    tpl = ContractTemplate(code="SUPPLY_FRAME_TEST", name_ru="Рамочный", body_storage_path="x",
                           variables_schema={"type": "object"}, version=1)
    spec_tpl = ContractTemplate(code="SPECIFICATION_V1", kind="specification", name_ru="Спецификация",
                                body_storage_path="s", variables_schema={"type": "object"}, version=1)
    db.add_all([tpl, spec_tpl])
    db.flush()
    contract = Contract(
        template_id=tpl.id, template_version=1, initiator_company_id=seller.id,
        counterparty_company_id=buyer.id, title="Рамочный", created_by_user_account_id=acc.id,
        variables={"contract_kind": kind, "contract_number": "346-01", "contract_date": "15.01.2026",
                   "amount_limit": "20000000000"},
        signing_provider="didox", status=ContractStatus(status),
    )
    db.add(contract)
    db.flush()
    return contract, acc


_SPEC_VARS = {"lines": [_AKFA_LINE], "price_basis": "with_vat", "vat_rate": "12", "payment_mode": "prepay"}


@requires_real_db
def test_specifications_are_numbered_within_their_contract(sf) -> None:  # noqa: ANN001
    from app.domains.contracts import specifications  # noqa: PLC0415

    session, _ = sf
    with session() as db:
        contract, acc = _frame(db)
        first = specifications.create_specification(db, contract, acc, dict(_SPEC_VARS), today=datetime.date(2026, 1, 15))
        second = specifications.create_specification(db, contract, acc, dict(_SPEC_VARS), today=datetime.date(2026, 2, 1))
        db.commit()

        assert (first.number, second.number) == (1, 2)
        assert first.status == "draft"
        assert first.amount_with_vat == D("1956000000.00")
        assert first.generated_document_path == f"contracts/{contract.public_id}/specification_1.pdf"


@requires_real_db
def test_its_goods_are_contract_lines(sf) -> None:  # noqa: ANN001
    from app.domains.contracts import specifications  # noqa: PLC0415
    from app.domains.contracts.models import ContractLine  # noqa: PLC0415

    session, _ = sf
    with session() as db:
        contract, acc = _frame(db)
        spec = specifications.create_specification(db, contract, acc, dict(_SPEC_VARS), today=datetime.date(2026, 1, 15))
        db.commit()
        [line] = db.query(ContractLine).filter(ContractLine.specification_id == spec.id).all()

    assert (line.contract_id, line.ord_no, line.qty, line.unit) == (contract.id, 1, D("120000"), "kg")
    assert (line.price, line.vat_rate, line.amount) == (D("14553.57"), 12, D("1746428571.43"))


@requires_real_db
def test_the_pdf_is_the_real_specification_form(sf) -> None:  # noqa: ANN001
    from app.domains.contracts import specifications  # noqa: PLC0415

    session, rendered = sf
    with session() as db:
        contract, acc = _frame(db)
        specifications.create_specification(db, contract, acc, dict(_SPEC_VARS), today=datetime.date(2026, 1, 15))

    [html] = rendered
    assert "Приложение № 1<br />к Договору № 346-01<br />от 15.01.2026" in html
    assert "СПЕЦИФИКАЦИЯ № 1 от 15.01.2026" in html
    assert "<td>14 553,57</td><td>1 746 428 571,43</td><td>209 571 428,57</td><td>1 956 000 000</td>" in html
    assert "один миллиард девятьсот пятьдесят шесть миллионов" in html
    assert "СП ООО «MGBUS»" in html and "{{" not in html


@requires_real_db
@pytest.mark.parametrize(("status", "kind"), [("pending_signatures", "frame"), ("active", "one_off")])
def test_only_a_signed_framework_contract_takes_specifications(sf, status, kind) -> None:  # noqa: ANN001
    from app.domains.contracts import specifications  # noqa: PLC0415

    session, _ = sf
    with session() as db:
        contract, acc = _frame(db, status=status, kind=kind)
        with pytest.raises(specifications.NotAFrameworkContract):
            specifications.create_specification(db, contract, acc, dict(_SPEC_VARS), today=datetime.date(2026, 1, 15))


def test_the_specification_body_validates() -> None:
    from app.domains.contracts import templates as template_service

    report = template_service.validate_body(_SPEC_BODY, "specification", {"properties": {}})
    assert report.ok, report.unknown


# ── at Didox: «Произвольный документ», subtype 8 «Спецификация» ───────────────


class _Didox:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict]] = []

    def create_document(self, doc_type, payload, **_):  # noqa: ANN001, ANN202
        from types import SimpleNamespace  # noqa: PLC0415

        self.created.append((doc_type, payload))
        return SimpleNamespace(didox_id="spec-hex", didox_contract_id=None)

    def info_by_tin(self, tin):  # noqa: ANN001, ANN202
        from types import SimpleNamespace  # noqa: PLC0415

        return SimpleNamespace(name=f"REG {tin}", address="Навои", director="X", director_pinfl="1" * 14)

    def archive(self, didox_id, **_):  # noqa: ANN001, ANN202
        return b"zip"


def _specification(db, contract, acc):  # noqa: ANN001, ANN202
    from app.domains.contracts import specifications  # noqa: PLC0415

    return specifications.create_specification(
        db, contract, acc, dict(_SPEC_VARS), today=datetime.date(2026, 1, 15)
    )


@requires_real_db
def test_the_seller_sends_it_to_didox_as_a_specification(sf, monkeypatch) -> None:  # noqa: ANN001
    import base64  # noqa: PLC0415

    from app.domains.edi import onboarding, specification_docs  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    monkeypatch.setattr(onboarding, "_is_live", lambda: True)
    monkeypatch.setattr(storage_service, "get_object_bytes", lambda path: b"%PDF-spec")
    session, _ = sf
    didox = _Didox()
    with session() as db:
        contract, acc = _frame(db)
        spec = _specification(db, contract, acc)
        row = specification_docs.create_for_specification(
            db, spec, acting_company_id=contract.initiator_company_id, account_id=acc.id,
            user_key="k", client=didox,
        )
        db.commit()

        assert (row.doc_type, row.subject_kind, row.subject_id) == ("000", "specification", spec.id)
        assert spec.status == "pending_signatures"
        # The stored payload is evidence of what we asserted — without the file.
        assert "document" not in row.payload

    [(doc_type, sent)] = didox.created
    assert doc_type == "000"
    data = sent["data"]
    assert data["Subtype"] == 8
    assert data["Document"] == {
        "DocumentNo": "1", "DocumentDate": "2026-01-15",
        "DocumentName": "Спецификация № 1 к договору № 346-01",
    }
    assert data["ContractDoc"] == {"ContractNo": "346-01", "ContractDate": "2026-01-15"}
    assert (data["SellerTin"], data["BuyerTin"]) == ("301111111", "302222222")
    assert sent["document"] == "data:application/pdf;base64," + base64.b64encode(b"%PDF-spec").decode()


@requires_real_db
def test_the_buyer_does_not_send_it(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.edi import contract_docs, onboarding, specification_docs  # noqa: PLC0415

    monkeypatch.setattr(onboarding, "_is_live", lambda: True)
    session, _ = sf
    with session() as db:
        contract, acc = _frame(db)
        spec = _specification(db, contract, acc)
        with pytest.raises(contract_docs.PartyMismatch):
            specification_docs.create_for_specification(
                db, spec, acting_company_id=contract.counterparty_company_id, account_id=acc.id,
                user_key="k", client=_Didox(),
            )


@requires_real_db
@pytest.mark.parametrize(("didox_status", "expected"), [(3, "active"), (4, "declined")])
def test_didox_decides_the_specification(sf, monkeypatch, didox_status, expected) -> None:  # noqa: ANN001
    from app.domains.edi import onboarding, specification_docs  # noqa: PLC0415
    from app.domains.edi import service as edi_service  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    monkeypatch.setattr(onboarding, "_is_live", lambda: True)
    monkeypatch.setattr(storage_service, "get_object_bytes", lambda path: b"%PDF-spec")
    monkeypatch.setattr(storage_service, "store_didox_archive", lambda did, blob: ("a", "sha"))
    session, _ = sf
    with session() as db:
        contract, acc = _frame(db)
        spec = _specification(db, contract, acc)
        didox = _Didox()
        row = specification_docs.create_for_specification(
            db, spec, acting_company_id=contract.initiator_company_id, account_id=acc.id,
            user_key="k", client=didox,
        )
        edi_service.apply_status(db, row, didox_status, user_key="k", client=didox)
        db.commit()
        assert spec.status == expected


# ── the portal routes ─────────────────────────────────────────────────────────


@pytest.fixture
def api(sf, monkeypatch):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.domains.edi import api_portal as edi_api  # noqa: PLC0415
    from app.domains.edi import onboarding  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415
    from tests._fake_redis import FakeRedis  # noqa: PLC0415

    session, _ = sf
    didox = _Didox()
    redis_ = FakeRedis()
    monkeypatch.setattr(onboarding, "_is_live", lambda: True)
    monkeypatch.setattr(edi_api, "get_didox_client", lambda: didox)
    monkeypatch.setattr(edi_api, "_guard", lambda db: None)
    monkeypatch.setattr(storage_service, "get_object_bytes", lambda path: b"%PDF-spec")
    monkeypatch.setattr(storage_service, "presign_object", lambda path, ttl=600: f"http://s3/{path}")
    app = create_app()

    def _db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    def _redis():  # noqa: ANN202
        yield redis_

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session, redis_, didox


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


@requires_real_db
def test_the_seller_draws_up_and_sends_a_specification(api) -> None:  # noqa: ANN001
    client, session, redis_, didox = api
    with session() as db:
        contract, acc = _frame(db)
        db.commit()
        cid, seller_id, acc_id = contract.id, contract.initiator_company_id, acc.id
    base = f"/api/v1/portal/contracts/{cid}/specifications"

    empty = client.get(base, headers=_auth(acc_id))
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"items": [], "can_create": True, "is_seller": True}

    bad = client.post(base, json={"variables": {"lines": [{"product": "", "qty": "1", "unit": "kg", "unit_price": "1"}]}}, headers=_auth(acc_id))
    assert bad.status_code == 422
    assert bad.json()["detail"] == {"error": "invalid_specification", "fields": ["lines.1.product"]}

    created = client.post(base, json={"variables": dict(_SPEC_VARS)}, headers=_auth(acc_id))
    assert created.status_code == 201, created.text
    spec = created.json()
    assert (spec["number"], spec["status"], spec["amount_with_vat"]) == (1, "draft", "1956000000.00")
    assert spec["lines"][0]["product"] == _AKFA_LINE["product"]

    pdf = client.get(f"{base}/{spec['id']}/document", params={"as": "url"}, headers=_auth(acc_id))
    assert pdf.json()["url"].endswith("specification_1.pdf")

    redis_.set("didox:user_key:301111111", "user-key")
    sent = client.post(
        f"/api/v1/portal/companies/{seller_id}/didox/specifications/{spec['id']}/document",
        headers=_auth(acc_id),
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["doc_type"] == "000"
    listed = client.get(base, headers=_auth(acc_id)).json()["items"][0]
    assert listed["status"] == "pending_signatures"
    assert listed["didox_document_id"] == sent.json()["id"]
    assert len(didox.created) == 1


@requires_real_db
def test_a_draft_specification_can_be_cancelled(api) -> None:  # noqa: ANN001
    client, session, _redis, _didox = api
    with session() as db:
        contract, acc = _frame(db)
        db.commit()
        cid, acc_id = contract.id, acc.id
    base = f"/api/v1/portal/contracts/{cid}/specifications"
    spec = client.post(base, json={"variables": dict(_SPEC_VARS)}, headers=_auth(acc_id)).json()

    cancelled = client.post(f"{base}/{spec['id']}/cancel", headers=_auth(acc_id))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
