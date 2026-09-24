"""A company's saved contract terms — «шаблоны условий» (real Postgres).

Every company has its own payment and delivery terms, and they used to be typed
again into every contract. A preset saves them once; choosing it fills the form.
The legal text stays the platform's template, so a preset holds only the terms.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_BASE = "/api/v1/portal/companies"
_SCHEMA = {
    "type": "object",
    "required": ["product", "qty", "price"],
    "properties": {
        "currency": {"enum": ["UZS", "USD"]},
        "incoterms": {"enum": ["EXW", "FCA", "DAP"]},
        "unit": {"enum": ["kg", "t"]},
    },
}
_TERMS = {
    "currency": "USD",
    "incoterms": "FCA",
    "payment_terms": "50% предоплата, 50% по факту",
    "delivery_window": "14 дней",
}


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    monkeypatch.setattr("app.domains.verification.service._dispatch_checks", lambda case_id: None)
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
        yield client, session
    clean(engine)


def _auth(account_id: int) -> dict[str, str]:
    from app.core.security import create_portal_access_token  # noqa: PLC0415

    return {"Authorization": f"Bearer {create_portal_access_token(subject=str(account_id))}"}


def _seed(session):  # noqa: ANN001, ANN202
    """Two verified companies, an owner and a plain member of the first, a template."""
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.companies.models import CompanyMember  # noqa: PLC0415
    from app.domains.contracts.models import ContractTemplate  # noqa: PLC0415
    from app.models.enums import CompanyMemberRole, CompanyStatus  # noqa: PLC0415

    with session() as db:
        owner = make_account(db, "+998900000001")
        member = make_account(db, "+998900000002")
        stranger = make_account(db, "+998900000003")
        company = company_service.create_company(db, owner, "UZ", "301111111")
        other = company_service.create_company(db, stranger, "UZ", "302222222")
        for c in (company, other):
            c.status = CompanyStatus.verified
            c.legal_name = f"OOO {c.tax_id}"
        db.add(
            CompanyMember(
                company_id=company.id, user_account_id=member.id,
                member_role=CompanyMemberRole.member,
            )
        )
        template = ContractTemplate(
            code="SUPPLY_TEST", name_ru="Договор", body_storage_path="x",
            variables_schema=_SCHEMA, version=1,
        )
        db.add(template)
        db.commit()
        return {
            "company": company.id,
            "other": other.id,
            "template": template.id,
            "owner": _auth(owner.id),
            "member": _auth(member.id),
            "stranger": _auth(stranger.id),
        }


def _create(client, ids, name="Стандарт", terms=None):  # noqa: ANN001, ANN202
    return client.post(
        f"{_BASE}/{ids['company']}/contract-term-presets",
        json={"name": name, "terms": terms if terms is not None else _TERMS},
        headers=ids["owner"],
    )


@requires_real_db
def test_an_owner_saves_lists_edits_and_archives_a_preset(api) -> None:  # noqa: ANN001
    client, session = api
    ids = _seed(session)

    created = _create(client, ids)
    assert created.status_code == 201, created.text
    preset = created.json()
    assert preset["name"] == "Стандарт"
    assert preset["terms"] == _TERMS

    listed = client.get(f"{_BASE}/{ids['company']}/contract-term-presets", headers=ids["owner"])
    assert listed.json()["can_edit"] is True
    assert [p["id"] for p in listed.json()["items"]] == [preset["id"]]

    edited = client.put(
        f"{_BASE}/{ids['company']}/contract-term-presets/{preset['id']}",
        json={"name": "Постоянным", "terms": {**_TERMS, "currency": "UZS"}},
        headers=ids["owner"],
    )
    assert edited.status_code == 200, edited.text
    assert (edited.json()["name"], edited.json()["terms"]["currency"]) == ("Постоянным", "UZS")

    archived = client.delete(
        f"{_BASE}/{ids['company']}/contract-term-presets/{preset['id']}", headers=ids["owner"]
    )
    assert archived.status_code == 204
    after = client.get(f"{_BASE}/{ids['company']}/contract-term-presets", headers=ids["owner"])
    assert after.json()["items"] == []


@requires_real_db
def test_a_member_reads_but_does_not_edit(api) -> None:  # noqa: ANN001
    client, session = api
    ids = _seed(session)
    preset = _create(client, ids).json()

    listed = client.get(f"{_BASE}/{ids['company']}/contract-term-presets", headers=ids["member"])
    assert listed.json()["can_edit"] is False
    assert len(listed.json()["items"]) == 1

    assert client.post(
        f"{_BASE}/{ids['company']}/contract-term-presets",
        json={"name": "X", "terms": _TERMS}, headers=ids["member"],
    ).status_code == 403
    assert client.delete(
        f"{_BASE}/{ids['company']}/contract-term-presets/{preset['id']}", headers=ids["member"]
    ).status_code == 403


@requires_real_db
def test_another_company_sees_nothing(api) -> None:  # noqa: ANN001
    client, session = api
    ids = _seed(session)
    preset = _create(client, ids).json()

    assert client.get(
        f"{_BASE}/{ids['company']}/contract-term-presets", headers=ids["stranger"]
    ).status_code == 404
    assert client.put(
        f"{_BASE}/{ids['other']}/contract-term-presets/{preset['id']}",
        json={"name": "X", "terms": _TERMS}, headers=ids["stranger"],
    ).status_code == 404


@requires_real_db
def test_only_terms_are_kept_and_checked(api) -> None:  # noqa: ANN001
    """Price, quantity and product belong to each deal, not to a preset — and a
    value outside the template's list would render a contract nobody can sign."""
    client, session = api
    ids = _seed(session)

    foreign_key = _create(client, ids, terms={**_TERMS, "price": "1000"})
    assert foreign_key.status_code == 422
    assert foreign_key.json()["detail"] == {"error": "invalid_terms", "fields": ["price"]}

    bad_enum = _create(client, ids, terms={**_TERMS, "incoterms": "XYZ"})
    assert bad_enum.status_code == 422
    assert bad_enum.json()["detail"]["fields"] == ["incoterms"]

    # Blank values are dropped rather than stored as "".
    blank = _create(client, ids, name="Пустой", terms={"currency": "USD", "special_conditions": " "})
    assert blank.status_code == 201
    assert blank.json()["terms"] == {"currency": "USD"}


@requires_real_db
def test_names_are_unique_per_company(api) -> None:  # noqa: ANN001
    client, session = api
    ids = _seed(session)
    _create(client, ids, name="Стандарт")

    again = _create(client, ids, name="стандарт")
    assert again.status_code == 409
    assert again.json()["detail"] == "preset_name_taken"


@requires_real_db
def test_a_contract_remembers_its_preset_and_refuses_someone_elses(api, monkeypatch) -> None:  # noqa: ANN001
    import hashlib  # noqa: PLC0415

    from app.domains.contracts import render as contract_render  # noqa: PLC0415
    from app.domains.contracts.models import Contract  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    monkeypatch.setattr(storage_service, "get_object_text", lambda path: "<p>{{ title }}</p>")
    monkeypatch.setattr(contract_render, "render_contract_pdf", lambda *a, **k: b"%PDF")
    monkeypatch.setattr(
        storage_service, "store_contract_pdf",
        lambda pid, n, pdf: (f"c/{pid}.pdf", hashlib.sha256(pdf).hexdigest()),
    )
    client, session = api
    ids = _seed(session)
    preset = _create(client, ids).json()
    body = {
        "initiator_company_id": ids["company"],
        "counterparty_company_id": ids["other"],
        "template_id": ids["template"],
        "variables": {"product": "PP", "qty": "5", "price": "900", **_TERMS},
    }

    mine = client.post(
        "/api/v1/portal/contracts", json={**body, "term_preset_id": preset["id"]},
        headers=ids["owner"],
    )
    assert mine.status_code == 201, mine.text
    with session() as db:
        assert db.get(Contract, mine.json()["id"]).term_preset_id == preset["id"]

    theirs = client.post(
        "/api/v1/portal/contracts",
        json={
            **body,
            "initiator_company_id": ids["other"],
            "counterparty_company_id": ids["company"],
            "term_preset_id": preset["id"],
        },
        headers=ids["stranger"],
    )
    assert theirs.status_code == 404
    assert theirs.json()["detail"] == "preset_not_found"
