"""Real-Postgres tests for eimzo_service (R3 Stage A — TA1.4/TA1.5 acceptance).

Guarded (localhost test_polymer). The gateway adapter (`verify_pkcs7`) and S3
storage are mocked; Redis is the in-memory fake. Covers: valid signature →
identity locked + evidence + encrypted person data + eimzo check passed +
auto-approve; pending_review when auto-approve off; INN mismatch; expired &
replayed (single-use) challenge; revoked cert → failed check; sidecar down → the
manual path stays usable; and PINFL never surfaced (masked only, evidence sha256).
"""

from __future__ import annotations

import base64
import hashlib

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

_PKCS7 = base64.b64encode(b"fake-pkcs7-blob").decode()


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _signer(**kw):  # noqa: ANN202
    from app.integrations.eimzo import EimzoSigner  # noqa: PLC0415

    defaults = {
        "org_name": "OOO Polymer Trade",
        "org_inn": "301234567",
        "full_name": "IVANOV IVAN",
        "pinfl": "31234567890123",
        "position": "Director",
        "serial_number": "AABBCC",
    }
    defaults.update(kw)
    return EimzoSigner(**defaults)


def _result(ok=True, revoked=False, error=None, **signer_kw):  # noqa: ANN001, ANN202
    from app.integrations.eimzo import EimzoVerifyResult  # noqa: PLC0415

    return EimzoVerifyResult(
        ok=ok, signer=_signer(**signer_kw), revoked=revoked, error=error
    )


def _company(db, tax="301234567", phone="+998900000001"):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415

    account = make_account(db, phone)
    company = company_service.create_company(db, account, "UZ", tax)
    verification_service.open_case(db, company)  # onboarding draft case (mirrors API)
    db.commit()  # persist setup so a later rollback (error paths) can't wipe it
    return account, company


def _patch(monkeypatch, result=None, raises=None):  # noqa: ANN001
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.integrations.eimzo import ProviderUnavailable  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    def fake_verify(pkcs7, challenge):  # noqa: ANN001, ANN202
        if raises is not None:
            raise ProviderUnavailable("down")
        return result

    monkeypatch.setattr(eimzo_service, "verify_pkcs7", fake_verify)
    monkeypatch.setattr(
        storage_service,
        "store_eimzo_pkcs7",
        lambda cid, b: (f"evidence/eimzo/{cid}/x.p7s", hashlib.sha256(b).hexdigest()),
    )


# ── happy path ────────────────────────────────────────────────────────────────


@requires_real_db
def test_valid_signature_auto_approves(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.domains.contracts.eimzo_models import (  # noqa: PLC0415
        CompanyPersonData,
        SignatureEvidence,
    )
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        CompanyStatus,
        VerificationCaseStatus,
        VerificationCheckStatus,
        VerificationCheckType,
    )
    from app.services import settings_service  # noqa: PLC0415

    _patch(monkeypatch, result=_result())
    with sf() as db:
        settings_service.set_many(db, {"verification_auto_approve": True}, None)
        account, company = _company(db)
        redis_client = FakeRedis()
        eimzo_service.issue_challenge(redis_client, company.id, account.id)

        outcome = eimzo_service.verify(db, redis_client, company, account, _PKCS7)
        db.commit()

        assert outcome.ok is True
        assert outcome.holder_masked == "****0123"

        company = db.get(Company, company.id)
        assert company.identity_locked is True
        assert company.legal_name == "OOO Polymer Trade"
        assert company.director_name == "IVANOV IVAN"
        assert company.status == CompanyStatus.verified

        case = db.get(type(outcome.case), outcome.case.id)
        assert case.status == VerificationCaseStatus.approved

        eimzo_check = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == case.id,
                VerificationCheck.check_type == VerificationCheckType.eimzo_signature,
            )
            .one()
        )
        assert eimzo_check.status == VerificationCheckStatus.passed
        assert eimzo_check.result["method"] == "eimzo"
        # PINFL never in the check payload in the clear.
        assert "31234567890123" not in str(eimzo_check.result)

        evidence = db.query(SignatureEvidence).filter_by(company_id=company.id).one()
        assert evidence.pkcs7_sha256 == hashlib.sha256(b"fake-pkcs7-blob").hexdigest()
        assert evidence.purpose == "company_identity"
        # PINFL / full name not stored in the clear cert_subject.
        assert "31234567890123" not in str(evidence.cert_subject)
        assert "IVANOV" not in str(evidence.cert_subject)

        person = db.query(CompanyPersonData).filter_by(company_id=company.id).one()
        assert person.pinfl_last4 == "0123"
        assert person.pinfl_enc and person.full_name_enc
        assert bytes(person.pinfl_enc) != b"31234567890123"  # encrypted


@requires_real_db
def test_evidence_signed_at_is_the_signing_moment_not_cert_issuance(sf, monkeypatch) -> None:  # noqa: ANN001
    """`signed_at` must record WHEN the signature was made.

    The certificate's validity window starts whenever the cert was issued — often
    years earlier — so recording `cert_valid_from` there misdates the evidence a
    lawyer reads as "signed on". Contract evidence already stamps the signing
    moment; identity evidence must match.
    """
    import datetime  # noqa: PLC0415

    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.domains.contracts.eimzo_models import SignatureEvidence  # noqa: PLC0415

    issued = datetime.datetime(2019, 3, 4, tzinfo=datetime.UTC)
    result = _result()
    object.__setattr__(result, "cert_valid_from", issued)

    _patch(monkeypatch, result=result)
    with sf() as db:
        account, company = _company(db)
        redis_client = FakeRedis()
        eimzo_service.issue_challenge(redis_client, company.id, account.id)
        before = datetime.datetime.now(datetime.UTC)
        eimzo_service.verify(db, redis_client, company, account, _PKCS7)
        db.commit()

        evidence = db.query(SignatureEvidence).filter_by(company_id=company.id).one()
        assert evidence.signed_at is not None
        assert evidence.signed_at != issued
        assert evidence.signed_at >= before - datetime.timedelta(seconds=5)


@requires_real_db
def test_locked_requisites_reject_manual_patch(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415

    _patch(monkeypatch, result=_result())
    with sf() as db:
        account, company = _company(db)
        redis_client = FakeRedis()
        eimzo_service.issue_challenge(redis_client, company.id, account.id)
        outcome = eimzo_service.verify(db, redis_client, company, account, _PKCS7)
        # send the pending_review case back to needs_info so the profile is editable
        verification_service.request_info(db, outcome.case, note="need more")
        db.commit()

        # legal_name / director_name are frozen by the signature even while editable
        with pytest.raises(company_service.IdentityLocked):
            company_service.update_profile(db, company, account, legal_name="Hacked LLC")
        db.rollback()
        # a non-locked field (short_name) is still editable
        company_service.update_profile(db, company, account, short_name="Polymer")
        db.commit()
        assert company.short_name == "Polymer"


@requires_real_db
def test_valid_signature_pending_review_when_auto_approve_off(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.models.enums import CompanyStatus, VerificationCaseStatus  # noqa: PLC0415

    _patch(monkeypatch, result=_result())
    with sf() as db:
        account, company = _company(db)
        redis_client = FakeRedis()
        eimzo_service.issue_challenge(redis_client, company.id, account.id)
        outcome = eimzo_service.verify(db, redis_client, company, account, _PKCS7)
        db.commit()

        assert outcome.ok is True
        case = db.get(type(outcome.case), outcome.case.id)
        assert case.status == VerificationCaseStatus.pending_review
        assert db.get(Company, company.id).status == CompanyStatus.pending_verification


# ── failure / mismatch / degradation ──────────────────────────────────────────


@requires_real_db
def test_inn_mismatch_raises_and_stores_no_evidence(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.domains.contracts.eimzo_models import SignatureEvidence  # noqa: PLC0415

    _patch(monkeypatch, result=_result(org_inn="300000000"))  # cert INN ≠ company tax_id
    with sf() as db:
        account, company = _company(db, tax="301234567")
        redis_client = FakeRedis()
        eimzo_service.issue_challenge(redis_client, company.id, account.id)

        with pytest.raises(eimzo_service.CertCompanyMismatch) as exc:
            eimzo_service.verify(db, redis_client, company, account, _PKCS7)
        # both values masked
        assert "300000000" not in exc.value.cert_inn_masked
        db.rollback()

        assert db.query(SignatureEvidence).filter_by(company_id=company.id).count() == 0
        assert db.get(Company, company.id).identity_locked is False


@requires_real_db
def test_missing_challenge_raises_expired(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415

    _patch(monkeypatch, result=_result())
    with sf() as db:
        account, company = _company(db)
        redis_client = FakeRedis()  # no challenge issued
        with pytest.raises(eimzo_service.ChallengeExpired):
            eimzo_service.verify(db, redis_client, company, account, _PKCS7)


@requires_real_db
def test_replayed_challenge_is_single_use(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415

    _patch(monkeypatch, result=_result())
    with sf() as db:
        account, company = _company(db)
        redis_client = FakeRedis()
        eimzo_service.issue_challenge(redis_client, company.id, account.id)
        eimzo_service.verify(db, redis_client, company, account, _PKCS7)
        db.commit()
        # replay: the challenge was consumed
        with pytest.raises(eimzo_service.ChallengeExpired):
            eimzo_service.verify(db, redis_client, company, account, _PKCS7)


@requires_real_db
def test_revoked_cert_records_failed_check(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import VerificationCheckStatus, VerificationCheckType  # noqa: PLC0415

    _patch(monkeypatch, result=_result(ok=False, revoked=True, error="cert_revoked"))
    with sf() as db:
        account, company = _company(db)
        redis_client = FakeRedis()
        eimzo_service.issue_challenge(redis_client, company.id, account.id)
        outcome = eimzo_service.verify(db, redis_client, company, account, _PKCS7)
        db.commit()

        assert outcome.ok is False
        assert outcome.reason == "cert_revoked"
        assert db.get(Company, company.id).identity_locked is False
        check = (
            db.query(VerificationCheck)
            .filter(VerificationCheck.check_type == VerificationCheckType.eimzo_signature)
            .one()
        )
        assert check.status == VerificationCheckStatus.failed
        assert check.result["reason"] == "cert_revoked"


@requires_real_db
def test_sidecar_down_propagates_and_manual_path_still_works(sf, monkeypatch) -> None:  # noqa: ANN001
    from app.domains.contracts import eimzo as eimzo_service  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.integrations.eimzo import ProviderUnavailable  # noqa: PLC0415
    from app.models.enums import VerificationCaseStatus  # noqa: PLC0415

    _patch(monkeypatch, raises=True)
    monkeypatch.setattr(verification_service, "_dispatch_checks", lambda case_id: None)
    with sf() as db:
        account, company = _company(db)
        redis_client = FakeRedis()
        eimzo_service.issue_challenge(redis_client, company.id, account.id)

        with pytest.raises(ProviderUnavailable):
            eimzo_service.verify(db, redis_client, company, account, _PKCS7)
        db.rollback()

        # The manual submit path is still usable after a sidecar outage.
        case = verification_service.submit_case(db, company, account)
        db.commit()
        assert case.status == VerificationCaseStatus.checks_running
