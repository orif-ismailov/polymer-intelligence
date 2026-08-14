"""Real-Postgres tests for the contract hardening beats (R3 Stage B — TB4.1/TB4.2)."""

from __future__ import annotations

import hashlib

import pytest
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


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _contract(db, status, **kw):  # noqa: ANN001, ANN202
    from app.domains.contracts.models import Contract, ContractTemplate  # noqa: PLC0415

    owner = make_account(db, kw.pop("phone_a", "+998900000001"))
    owner2 = make_account(db, kw.pop("phone_b", "+998900000002"))
    a = make_company(db, owner, tax_id=kw.pop("tax_a", "301111111"))
    b = make_company(db, owner2, tax_id=kw.pop("tax_b", "302222222"))
    tpl = ContractTemplate(
        code=kw.pop("code", "X"), name_ru="Договор", body_storage_path="x",
        variables_schema={}, version=1, is_active=True,
    )
    db.add(tpl)
    db.flush()
    contract = Contract(
        template_id=tpl.id, template_version=1, initiator_company_id=a.id,
        counterparty_company_id=b.id, title="Договор", variables={},
        status=status, created_by_user_account_id=owner.id, **kw,
    )
    db.add(contract)
    db.flush()
    return contract


@requires_real_db
def test_expire_stale_contracts(engine, sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts.models import Contract  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415
    from app.tasks import contracts as contracts_task  # noqa: PLC0415

    monkeypatch.setattr("app.core.db.SessionLocal", session_factory(engine))
    with sf() as db:
        stale = _contract(db, ContractStatus.pending_signatures)
        fresh = _contract(db, ContractStatus.pending_counterparty, code="Y", tax_a="303333333", tax_b="304444444", phone_a="+998900000003", phone_b="+998900000004")
        db.commit()
        stale_id, fresh_id = stale.id, fresh.id
        db.execute(
            sa.text("UPDATE contracts SET updated_at = now() - interval '40 days' WHERE id = :id"),
            {"id": stale_id},
        )
        db.commit()

    result = contracts_task.expire_stale_contracts()
    assert stale_id in result["expired"]
    assert fresh_id not in result["expired"]

    with sf() as db:
        assert db.get(Contract, stale_id).status == ContractStatus.expired
        assert db.get(Contract, fresh_id).status == ContractStatus.pending_counterparty


@requires_real_db
def test_verify_contract_integrity_detects_tamper(engine, sf, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415
    from app.tasks import contracts as contracts_task  # noqa: PLC0415

    monkeypatch.setattr("app.core.db.SessionLocal", session_factory(engine))
    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", None)  # no alert send
    good = b"%PDF-good-bytes"
    with sf() as db:
        ok = _contract(
            db, ContractStatus.active,
            generated_document_path="contracts/ok/v1.pdf",
            document_sha256=hashlib.sha256(good).hexdigest(),
        )
        tampered = _contract(
            db, ContractStatus.active, code="Y", tax_a="303333333", tax_b="304444444",
            phone_a="+998900000003", phone_b="+998900000004",
            generated_document_path="contracts/bad/v1.pdf",
            document_sha256="0" * 64,  # stored hash won't match the bytes
        )
        db.commit()
        ok_id, bad_id = ok.id, tampered.id

    # storage returns the same "good" bytes for every path: ok matches, tampered doesn't
    monkeypatch.setattr(storage_service, "get_object_bytes", lambda key: good)

    result = contracts_task.verify_contract_integrity()
    assert result["checked"] == 2
    assert bad_id in result["mismatches"]
    assert ok_id not in result["mismatches"]
