"""Registry checks inside a verification case (R6 / P7.c — T5.2–T5.4).

Guarded (test_polymer). Three things are under test here, and the first is a bug
this wave had to fix before it could add a check that goes `unavailable` at all.

**T5.2 — the evaluator used to stall forever on `unavailable`.**
`on_check_completed` treats `unavailable` as "not finished yet", and
`approve()` only works from `pending_review`. So a check that exhausted its five
retries pinned the case in `checks_running` and the MANUAL path stopped working —
a direct violation of the R1 invariant that a dead provider never blocks manual
verification. R1 shipped safely only because none of its checks could fail that
way; the registry checks can. The fix is narrow: `unavailable` blocks while
retries remain and stops blocking once they are exhausted.

**T5.3 — registry checks are not spawned into a void.** `submit_case` adds them
only on the live rail; on the stub rail (the shipped default) they appear when an
operator records a manual snapshot. So a case can never sit waiting for a channel
we do not have.

**T5.4 — the operator path.** Staff transcribe an open service (my.soliq.uz,
license.gov.uz), optionally attach a screenshot, and the case re-evaluates. This
is the half of P7.c that works today.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_staff,
    migrate_head,
    requires_real_db,
    session_factory,
)
from tests.conftest import set_switch

_A = "/api/v1/admin"


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _submit(db, monkeypatch=None, phone="+998900000001", tax="301234567"):  # noqa: ANN001, ANN202
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415

    account = make_account(db, phone)
    company = company_service.create_company(db, account, "UZ", tax)
    company.legal_name = 'ООО "ПОЛИМЕР ТРЕЙД"'
    db.flush()
    verification_service.open_case(db, company)
    with patch.object(verification_service, "_dispatch_checks", lambda case_id: None):
        case = verification_service.submit_case(db, company, account)
    return account, company, case


def _check_types(db, case_id) -> set[str]:  # noqa: ANN001
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415

    return {
        c.check_type.value
        for c in db.query(VerificationCheck).filter(VerificationCheck.case_id == case_id).all()
    }


def _resolve_automated(db, case_id, status) -> None:  # noqa: ANN001
    """Put every non-manual check into `status` (the R1 helper, reused)."""
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import VerificationCheckType  # noqa: PLC0415

    for check in db.query(VerificationCheck).filter(VerificationCheck.case_id == case_id).all():
        if check.check_type != VerificationCheckType.manual_kyb:
            check.status = status
    db.flush()


# ── T5.2: the evaluator no longer stalls on an exhausted check ────────────────


@requires_real_db
def test_an_unavailable_check_with_retries_left_still_holds_the_case(sf) -> None:  # noqa: ANN001
    """Mid-retry is genuinely "not finished" — the case must wait."""
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        VerificationCaseStatus,
        VerificationCheckStatus,
        VerificationCheckType,
    )

    with sf() as db:
        _account, _company, case = _submit(db)
        _resolve_automated(db, case.id, VerificationCheckStatus.passed)
        stuck = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == case.id,
                VerificationCheck.check_type == VerificationCheckType.tax_id_format,
            )
            .one()
        )
        stuck.status = VerificationCheckStatus.unavailable
        stuck.attempts = 2
        db.flush()

        verification_service.on_check_completed(db, case.id)
        db.commit()
        db.refresh(case)

        assert case.status == VerificationCaseStatus.checks_running


@requires_real_db
def test_an_exhausted_unavailable_check_no_longer_pins_the_case(sf) -> None:  # noqa: ANN001
    """The R1 latent bug: five failed attempts used to lock the case in
    `checks_running`, where `approve()` cannot reach it — so a dead provider
    silently disabled the manual path it was supposed to leave open."""
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        VerificationCaseStatus,
        VerificationCheckStatus,
        VerificationCheckType,
    )

    with sf() as db:
        _account, _company, case = _submit(db)
        _resolve_automated(db, case.id, VerificationCheckStatus.passed)
        dead = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == case.id,
                VerificationCheck.check_type == VerificationCheckType.tax_id_format,
            )
            .one()
        )
        dead.status = VerificationCheckStatus.unavailable
        dead.attempts = verification_service.MAX_CHECK_ATTEMPTS
        db.flush()

        verification_service.on_check_completed(db, case.id)
        db.commit()
        db.refresh(case)

        assert case.status == VerificationCaseStatus.pending_review, (
            "a human must be able to decide the case a dead provider left behind"
        )


@requires_real_db
def test_a_case_a_dead_provider_left_behind_can_be_approved(sf) -> None:  # noqa: ANN001
    """The invariant end to end: manual verification still completes."""
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        CompanyStatus,
        VerificationCheckStatus,
        VerificationCheckType,
    )

    with sf() as db:
        _account, company, case = _submit(db)
        staff = make_staff(db)
        _resolve_automated(db, case.id, VerificationCheckStatus.passed)
        dead = (
            db.query(VerificationCheck)
            .filter(
                VerificationCheck.case_id == case.id,
                VerificationCheck.check_type == VerificationCheckType.documents_complete,
            )
            .one()
        )
        dead.status = VerificationCheckStatus.unavailable
        dead.attempts = verification_service.MAX_CHECK_ATTEMPTS
        db.flush()
        verification_service.on_check_completed(db, case.id)
        db.commit()

        verification_service.approve(db, case, staff_user_id=staff.id, note="manual review")
        db.commit()
        db.refresh(company)

        assert company.status == CompanyStatus.verified


@requires_real_db
def test_the_retry_budget_is_one_number_in_one_place(sf) -> None:  # noqa: ANN001
    """The task's `max_retries` and the evaluator's cut-off must not drift."""
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.tasks.verification import run_single_check  # noqa: PLC0415

    assert run_single_check.max_retries == verification_service.MAX_CHECK_ATTEMPTS


# ── T5.3: registry checks are not spawned into a void ────────────────────────


@requires_real_db
def test_the_stub_rail_spawns_no_registry_checks(sf) -> None:  # noqa: ANN001
    """`gov_registry_mode` ships `stub`, so submitting a case is unchanged from R1."""
    with sf() as db:
        _account, _company, case = _submit(db)
        db.commit()

        assert _check_types(db, case.id) == {
            "tax_id_format",
            "bank_requisites",
            "documents_complete",
            "manual_kyb",
        }


@requires_real_db
def test_the_live_rail_spawns_both_registry_checks(sf) -> None:  # noqa: ANN001
    with sf() as db:
        set_switch(gov_registry_mode="live")
        db.flush()
        _account, _company, case = _submit(db)
        db.commit()

        assert {"gov_registry", "vat_status"} <= _check_types(db, case.id)


# ── T5.4: the operator's manual check ────────────────────────────────────────


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
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


def _staff_headers(session, role="analyst", email="reg@example.com"):  # noqa: ANN001, ANN202
    from app.core.security import create_access_token  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, email)
        staff.is_admin = role == "admin"
        db.commit()
        staff_id = staff.id
    return {"Authorization": f"Bearer {create_access_token(subject=str(staff_id))}"}


def _case(session):  # noqa: ANN001, ANN202
    with session() as db:
        _account, company, case = _submit(db)
        db.commit()
        return {"case_id": case.id, "company_id": company.id}


_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_the_route_is_registered() -> None:
    from app.domains.verification.api_admin import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/admin/verification/cases/{case_id}/registry-check" in paths


@requires_real_db
def test_an_operator_records_a_company_check_and_the_case_reevaluates(api) -> None:  # noqa: ANN001
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.domains.verification.registry_models import RegistrySnapshot  # noqa: PLC0415
    from app.models.enums import VerificationCheckStatus  # noqa: PLC0415

    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)

    response = client.post(
        f"{_A}/verification/cases/{scene['case_id']}/registry-check",
        headers=headers,
        data={
            "kind": "company",
            "status": "active",
            "raw_status": "ДЕЙСТВУЮЩЕЕ",
            "name": 'ООО "Полимер Трейд"',
            "director": "Иванов И.И.",
            "note": "проверено на registr.stat.uz",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["check_status"] == "passed"

    with session() as db:
        snapshot = db.query(RegistrySnapshot).one()
        assert snapshot.source == "manual"
        assert snapshot.created_by is not None, "a transcription has an author"
        assert snapshot.payload["status"] == "active"
        assert snapshot.note == "проверено на registr.stat.uz"

        check = (
            db.query(VerificationCheck)
            .filter(VerificationCheck.case_id == scene["case_id"])
            .filter(VerificationCheck.check_type == "gov_registry")
            .one()
        )
        assert check.status == VerificationCheckStatus.passed
        assert check.result["registry_name"] == 'ООО "Полимер Трейд"'


@requires_real_db
def test_a_liquidated_company_fails_the_check_and_the_case_needs_info(api) -> None:  # noqa: ANN001
    from app.domains.verification.models import VerificationCase  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        VerificationCaseStatus,
        VerificationCheckStatus,
    )

    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)

    # Resolve the R1 checks first so the evaluator can reach a verdict.
    with session() as db:
        _resolve_automated(db, scene["case_id"], VerificationCheckStatus.passed)
        db.commit()

    response = client.post(
        f"{_A}/verification/cases/{scene['case_id']}/registry-check",
        headers=headers,
        data={"kind": "company", "status": "liquidated", "raw_status": "ЛИКВИДИРОВАНО"},
    )

    assert response.status_code == 200
    assert response.json()["check_status"] == "failed"
    with session() as db:
        case = db.get(VerificationCase, scene["case_id"])
        assert case is not None
        assert case.status == VerificationCaseStatus.needs_info


@requires_real_db
def test_a_vat_check_records_the_certificate(api) -> None:  # noqa: ANN001
    from app.domains.verification.registry_models import RegistrySnapshot  # noqa: PLC0415

    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)

    response = client.post(
        f"{_A}/verification/cases/{scene['case_id']}/registry-check",
        headers=headers,
        data={"kind": "vat", "registered": "true", "certificate_no": "3012345670001"},
    )

    assert response.status_code == 200
    assert response.json()["check_status"] == "passed"
    with session() as db:
        snapshot = db.query(RegistrySnapshot).filter(RegistrySnapshot.kind == "vat").one()
        assert snapshot.payload["certificate_no"] == "3012345670001"


@requires_real_db
def test_a_company_that_is_not_a_vat_payer_is_a_warning(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)

    response = client.post(
        f"{_A}/verification/cases/{scene['case_id']}/registry-check",
        headers=headers,
        data={"kind": "vat", "registered": "false"},
    )
    assert response.json()["check_status"] == "warning"


@requires_real_db
def test_a_screenshot_is_stored_with_its_hash(api) -> None:  # noqa: ANN001
    """The operator's evidence gets the same treatment as a PKCS#7."""
    from app.domains.verification.registry_models import RegistrySnapshot  # noqa: PLC0415

    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)

    with patch("app.core.storage.s3_client") as s3:
        response = client.post(
            f"{_A}/verification/cases/{scene['case_id']}/registry-check",
            headers=headers,
            data={"kind": "company", "status": "active"},
            files={"evidence": ("soliq.png", io.BytesIO(_PNG), "image/png")},
        )

    assert response.status_code == 200, response.text
    key = s3.put_object.call_args.kwargs["Key"]
    assert key.startswith(f"evidence/registry/{scene['company_id']}/")
    assert key.endswith(".png"), "the extension comes from the magic bytes, not the filename"
    with session() as db:
        snapshot = db.query(RegistrySnapshot).one()
        assert snapshot.evidence_path is not None
        assert snapshot.evidence_sha256 is not None
        assert len(snapshot.evidence_sha256) == 64


@requires_real_db
def test_an_unacceptable_screenshot_is_refused(api) -> None:  # noqa: ANN001
    from app.domains.verification.registry_models import RegistrySnapshot  # noqa: PLC0415

    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)

    response = client.post(
        f"{_A}/verification/cases/{scene['case_id']}/registry-check",
        headers=headers,
        data={"kind": "company", "status": "active"},
        files={"evidence": ("hack.svg", io.BytesIO(b"<svg/>"), "image/svg+xml")},
    )

    assert response.status_code == 422
    with session() as db:
        assert db.query(RegistrySnapshot).count() == 0, "nothing is recorded on a refusal"


@requires_real_db
def test_re_checking_appends_a_second_snapshot(api) -> None:  # noqa: ANN001
    from app.domains.verification.registry_models import RegistrySnapshot  # noqa: PLC0415

    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)
    url = f"{_A}/verification/cases/{scene['case_id']}/registry-check"

    client.post(url, headers=headers, data={"kind": "company", "status": "active"})
    client.post(url, headers=headers, data={"kind": "company", "status": "liquidated"})

    with session() as db:
        assert db.query(RegistrySnapshot).count() == 2


@requires_real_db
def test_an_unknown_kind_is_refused(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)

    response = client.post(
        f"{_A}/verification/cases/{scene['case_id']}/registry-check",
        headers=headers,
        data={"kind": "horoscope"},
    )
    assert response.status_code == 422


@requires_real_db
def test_the_check_needs_authentication(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _case(session)
    response = client.post(
        f"{_A}/verification/cases/{scene['case_id']}/registry-check",
        data={"kind": "company", "status": "active"},
    )
    assert response.status_code in {401, 403}


@requires_real_db
def test_the_case_page_shows_the_latest_snapshot_of_each_kind(api) -> None:  # noqa: ANN001
    client, session = api
    scene = _case(session)
    headers = _staff_headers(session)
    url = f"{_A}/verification/cases/{scene['case_id']}/registry-check"

    client.post(url, headers=headers, data={"kind": "company", "status": "active"})
    client.post(url, headers=headers, data={"kind": "vat", "registered": "true"})

    body = client.get(f"{_A}/verification/cases/{scene['case_id']}", headers=headers).json()
    registry = body["registry"]
    assert registry["company"]["payload"]["status"] == "active"
    assert registry["company"]["source"] == "manual"
    assert registry["vat"]["payload"]["registered"] is True
    assert "licenses" not in registry
