"""Real-Postgres tests for contract_service (R3 Stage B — TB1.2 acceptance).

Guarded (localhost test_polymer). WeasyPrint/S3 are stubbed (render is separately
tested); the E-IMZO adapter is faked to echo a base64-JSON "pkcs7". Covers:
both-verified enforcement, typed variables validation, the transition table,
INN-mismatch signing rejection, exactly-once activation on both signatures, the
challenge/re-render invalidation, and cancel-after-signature blocking.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
import sqlalchemy as sa

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)

_SCHEMA = {
    "type": "object",
    "required": ["product", "qty", "unit"],
    "properties": {"unit": {"enum": ["kg", "t"]}},
}
_VARS = {"product": "HDPE", "qty": "20", "unit": "t"}


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _verified_company(db, tax, phone, **kw):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = company_service.create_company(db, account, "UZ", tax)
    company.status = CompanyStatus.verified
    company.legal_name = kw.get("legal_name", f"OOO {tax}")
    db.flush()
    return account, company


def _template(db):  # noqa: ANN001, ANN202
    from app.domains.contracts.models import ContractTemplate  # noqa: PLC0415

    tpl = ContractTemplate(
        code="SUPPLY_TEST",
        name_ru="Договор",
        body_storage_path="contracts/templates/x.html",
        variables_schema=_SCHEMA,
        version=1,
        is_active=True,
    )
    db.add(tpl)
    db.flush()
    return tpl


def _patch(monkeypatch):  # noqa: ANN001
    """Stub S3 + WeasyPrint + the E-IMZO adapter for the service under test."""
    from app.domains.contracts import render as contract_render  # noqa: PLC0415
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.integrations.eimzo import EimzoSigner, EimzoVerifyResult  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    monkeypatch.setattr(storage_service, "get_object_text", lambda path: "<p>{{ title }}</p>")
    monkeypatch.setattr(contract_render, "render_contract_pdf", lambda *a, **k: b"%PDF-fake-doc")
    monkeypatch.setattr(
        storage_service, "store_contract_pdf",
        lambda pid, n, pdf: (f"contracts/{pid}/contract_v{n}.pdf", hashlib.sha256(pdf).hexdigest()),
    )
    monkeypatch.setattr(
        storage_service, "store_eimzo_pkcs7",
        lambda cid, b: (f"evidence/eimzo/{cid}/x.p7s", hashlib.sha256(b).hexdigest()),
    )

    def fake_verify(pkcs7, challenge):  # noqa: ANN001, ANN202
        blob = json.loads(base64.b64decode(pkcs7))
        ok = blob.get("challenge") == challenge
        return EimzoVerifyResult(
            ok=ok,
            signer=EimzoSigner(org_inn=blob.get("tin")),
            error=None if ok else "signature_invalid",
        )

    monkeypatch.setattr(contract_service, "verify_pkcs7", fake_verify)


def _pkcs7(challenge: str, tin: str) -> str:
    return base64.b64encode(json.dumps({"challenge": challenge, "tin": tin}).encode()).decode()


# ── create / validation ───────────────────────────────────────────────────────


@requires_real_db
def test_create_requires_both_verified(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        acc_a, comp_a = _verified_company(db, "301111111", "+998900000001")
        _acc_b, comp_b = _verified_company(db, "302222222", "+998900000002")
        comp_b.status = CompanyStatus.draft  # not verified
        db.flush()
        tpl = _template(db)
        with pytest.raises(contract_service.CompanyNotVerified):
            contract_service.create_contract(db, comp_a, acc_a, tpl, _VARS, comp_b)


@requires_real_db
def test_create_invalid_variables_typed(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        acc_a, comp_a = _verified_company(db, "301111111", "+998900000001")
        _acc_b, comp_b = _verified_company(db, "302222222", "+998900000002")
        tpl = _template(db)
        with pytest.raises(contract_service.VariablesInvalid) as exc:
            contract_service.create_contract(db, comp_a, acc_a, tpl, {"product": "HDPE", "unit": "x"}, comp_b)
        assert "qty" in exc.value.fields  # missing required
        assert "unit" in exc.value.fields  # bad enum


# ── transitions + signing ─────────────────────────────────────────────────────


def _make_sent_pending(db, monkeypatch):  # noqa: ANN001, ANN202
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    acc_a, comp_a = _verified_company(db, "301111111", "+998900000001")
    acc_b, comp_b = _verified_company(db, "302222222", "+998900000002")
    tpl = _template(db)
    contract = contract_service.create_contract(db, comp_a, acc_a, tpl, _VARS, comp_b)
    contract_service.send(db, contract, acc_a)
    contract_service.accept_terms(db, contract, acc_b)
    return (acc_a, comp_a), (acc_b, comp_b), contract


@requires_real_db
def test_transition_table_and_illegal(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        (acc_a, _comp_a), _b, contract = _make_sent_pending(db, monkeypatch)
        assert contract.status == ContractStatus.pending_signatures
        # illegal: cannot accept again from pending_signatures
        with pytest.raises(contract_service.InvalidContractTransition):
            contract_service.accept_terms(db, contract, acc_a)


@requires_real_db
def test_full_sign_activates(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        (acc_a, comp_a), (acc_b, comp_b), contract = _make_sent_pending(db, monkeypatch)
        redis_client = FakeRedis()

        ch_a = contract_service.issue_sign_challenge(db, redis_client, contract, comp_a, acc_a)
        contract_service.sign(db, redis_client, contract, comp_a, acc_a, _pkcs7(ch_a, comp_a.tax_id))
        assert contract.status == ContractStatus.pending_signatures  # one side only

        ch_b = contract_service.issue_sign_challenge(db, redis_client, contract, comp_b, acc_b)
        contract_service.sign(db, redis_client, contract, comp_b, acc_b, _pkcs7(ch_b, comp_b.tax_id))
        db.commit()

        db.refresh(contract)
        assert contract.status == ContractStatus.active
        assert contract.activated_at is not None
        assert (
            db.query(DomainEvent)
            .filter(DomainEvent.event_type == event_types.CONTRACT_ACTIVATED)
            .count()
            == 1
        )


@requires_real_db
def test_concurrent_final_signatures_activate_exactly_once(sf, monkeypatch) -> None:  # noqa: ANN001
    """Both parties sign at the same moment → one activation, not two.

    The real race the `SELECT … FOR UPDATE` in `_maybe_activate` guards: each
    transaction inserts its own signature and then asks "are both present?". If
    both read before either commits, an unguarded implementation flips the row to
    `active` twice and emits two CONTRACT_ACTIVATED events. Two separate sessions
    on real Postgres are required — a single session can't reproduce it.
    """
    import threading  # noqa: PLC0415

    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.domains.contracts.models import Contract  # noqa: PLC0415
    from app.models.enums import ContractStatus  # noqa: PLC0415
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        (acc_a, comp_a), (acc_b, comp_b), contract = _make_sent_pending(db, monkeypatch)
        redis_client = FakeRedis()
        contract_id = contract.id
        # Issue both challenges up front so the threads only race on signing.
        ch_a = contract_service.issue_sign_challenge(db, redis_client, contract, comp_a, acc_a)
        ch_b = contract_service.issue_sign_challenge(db, redis_client, contract, comp_b, acc_b)
        ids = (comp_a.id, acc_a.id, comp_a.tax_id, comp_b.id, acc_b.id, comp_b.tax_id)
        db.commit()

    comp_a_id, acc_a_id, tax_a, comp_b_id, acc_b_id, tax_b = ids
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _sign(company_id: int, account_id: int, tax: str, challenge: str) -> None:
        from app.domains.accounts.models import UserAccount  # noqa: PLC0415
        from app.domains.companies.models import Company  # noqa: PLC0415

        try:
            with sf() as s:
                c = s.get(Contract, contract_id)
                company = s.get(Company, company_id)
                account = s.get(UserAccount, account_id)
                barrier.wait(timeout=10)  # release both threads together
                contract_service.sign(s, redis_client, c, company, account, _pkcs7(challenge, tax))
                s.commit()
        except BaseException as exc:  # noqa: BLE001 — surfaced below
            errors.append(exc)

    threads = [
        threading.Thread(target=_sign, args=(comp_a_id, acc_a_id, tax_a, ch_a)),
        threading.Thread(target=_sign, args=(comp_b_id, acc_b_id, tax_b, ch_b)),
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)

    assert not errors, f"concurrent signing raised: {errors}"

    with sf() as db:
        contract = db.get(Contract, contract_id)
        assert contract.status == ContractStatus.active
        assert contract.activated_at is not None
        assert (
            db.query(DomainEvent)
            .filter(
                DomainEvent.event_type == event_types.CONTRACT_ACTIVATED,
                DomainEvent.aggregate_id == str(contract_id),
            )
            .count()
            == 1
        )


@requires_real_db
def test_sign_inn_mismatch_rejected(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415
    from app.domains.contracts.eimzo import CertCompanyMismatch  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        (acc_a, comp_a), _b, contract = _make_sent_pending(db, monkeypatch)
        redis_client = FakeRedis()
        ch_a = contract_service.issue_sign_challenge(db, redis_client, contract, comp_a, acc_a)
        with pytest.raises(CertCompanyMismatch):
            contract_service.sign(db, redis_client, contract, comp_a, acc_a, _pkcs7(ch_a, "300000000"))


@requires_real_db
def test_rerender_invalidates_challenge(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        (acc_a, comp_a), _b, contract = _make_sent_pending(db, monkeypatch)
        redis_client = FakeRedis()
        ch_a = contract_service.issue_sign_challenge(db, redis_client, contract, comp_a, acc_a)
        # simulate a re-render: the document hash changes → outstanding challenge invalid
        contract.document_sha256 = "deadbeef"
        db.flush()
        with pytest.raises(contract_service.ChallengeExpired):
            contract_service.sign(db, redis_client, contract, comp_a, acc_a, _pkcs7(ch_a, comp_a.tax_id))


@requires_real_db
def test_cancel_blocked_after_signature(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import service as contract_service  # noqa: PLC0415

    _patch(monkeypatch)
    with sf() as db:
        (acc_a, comp_a), _b, contract = _make_sent_pending(db, monkeypatch)
        redis_client = FakeRedis()
        ch_a = contract_service.issue_sign_challenge(db, redis_client, contract, comp_a, acc_a)
        contract_service.sign(db, redis_client, contract, comp_a, acc_a, _pkcs7(ch_a, comp_a.tax_id))
        with pytest.raises(contract_service.CannotCancel):
            contract_service.cancel(db, contract, acc_a)
