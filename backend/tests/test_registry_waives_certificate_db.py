"""A company the state registry confirms needs no registration certificate.

Guarded (test_polymer). Three properties, each a way this change could go wrong:

**The registry checks must actually run on the Didox rail.** `_registry_checks_for`
used to spawn them only on `live`, a guard written when there were two rails. The
`didox` rail came later as a third and was never admitted, so on a deployment with
Didox switched on the registry did nothing but prefill the form — no verdict was
ever recorded on a case. Waiving a document on the strength of a check that never
runs would have verified companies on nothing.

**The documents check must wait for the registry verdict.** Checks fan out as
parallel tasks. Unordered, `documents_complete` could finish first, find no
registry pass, fail — and a failed automated check sends the case to `needs_info`,
which NOTIFIES the applicant, asking them for a certificate the very next check
was about to waive. So it is held back until the registry has answered.

**A registry that cannot confirm must leave the certificate required.** Not found,
liquidated, or simply down — each falls back to the document rule unchanged.

Run with:
    DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_polymer \
        uv run pytest tests/test_registry_waives_certificate_db.py -q
"""

from __future__ import annotations

from unittest.mock import patch

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
from tests.conftest import set_switch

_TAX = "301234567"
_NAME = 'ООО "ПОЛИМЕР ТРЕЙД"'


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine, monkeypatch):  # noqa: ANN001, ANN201
    clean(engine)
    monkeypatch.setattr("app.core.db.SessionLocal", session_factory(engine))
    yield session_factory(engine)
    clean(engine)


class _Registry:
    """A registry client that answers the way Didox does, without a network.

    Stubbed at the CLIENT, not at `fetch_and_record`, so the snapshot is written
    by the real `record_snapshot` and judged by the real `check_gov_registry`.
    """

    def __init__(self, status: str = "active", *, down: bool = False) -> None:
        self.status = status
        self.down = down

    def lookup_company(self, inn: str):  # noqa: ANN201
        from app.integrations import gov_registry  # noqa: PLC0415

        if self.down:
            raise gov_registry.ProviderUnavailable("didox down")
        return gov_registry.CompanySnapshot(inn=inn, name=_NAME, status=self.status)

    def lookup_vat(self, inn: str):  # noqa: ANN201, ARG002
        from app.integrations import gov_registry  # noqa: PLC0415

        if self.down:
            raise gov_registry.ProviderUnavailable("didox down")
        return gov_registry.VatSnapshot(registered=True, certificate_no="326080220838")

    def lookup_licenses(self, inn: str):  # noqa: ANN201, ARG002
        from app.integrations import gov_registry  # noqa: PLC0415

        raise gov_registry.ProviderUnavailable("no licence register")


def _didox_rail() -> None:
    set_switch(gov_registry_mode="didox", didox_partner_token="test-token")


def _submit(db, *, with_certificate: bool = False):  # noqa: ANN001, ANN202
    """A registered company with NO documents, submitted for verification."""
    from app.domains.companies import service as company_service  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationDocument  # noqa: PLC0415
    from app.models.enums import VerificationDocumentKind  # noqa: PLC0415

    account = make_account(db, "+998900000001")
    company = company_service.create_company(db, account, "UZ", _TAX)
    company.legal_name = _NAME
    if with_certificate:
        db.add(
            VerificationDocument(
                company_id=company.id,
                kind=VerificationDocumentKind.registration_certificate,
                storage_path="verification/x",
                sha256="z",
                uploaded_by_user_account_id=account.id,
            )
        )
    db.flush()
    verification_service.open_case(db, company)
    with patch.object(verification_service, "_dispatch_checks", lambda case_id: None):
        case = verification_service.submit_case(db, company, account)
    db.commit()
    return case.id


def _checks(db, case_id):  # noqa: ANN001, ANN202
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415

    return {
        c.check_type.value: c
        for c in db.query(VerificationCheck).filter(VerificationCheck.case_id == case_id).all()
    }


def _run_pipeline(case_id: int, dispatched: list[int] | None = None) -> None:
    """Run the fan-out and every task it (or a completed check) enqueues, in order.

    `_dispatch_single` is the one enqueue point; routing it through a FIFO here
    reproduces the real dependency without a broker, and records what was
    enqueued and when.
    """
    from app.tasks import verification as tasks  # noqa: PLC0415

    queue: list[int] = []

    def enqueue(check_id: int) -> None:
        queue.append(check_id)
        if dispatched is not None:
            dispatched.append(check_id)

    with patch.object(tasks, "_dispatch_single", enqueue):
        tasks.run_verification_checks.apply(args=[case_id]).get()
        while queue:
            tasks.run_single_check.apply(args=[queue.pop(0)])


def _needs_info_events(db, case_id) -> int:  # noqa: ANN001
    from app.services import event_types  # noqa: PLC0415

    return db.execute(
        sa.text(
            "SELECT count(*) FROM domain_events "
            "WHERE event_type = :t AND aggregate_id = :id"
        ),
        {"t": event_types.VERIFICATION_CASE_NEEDS_INFO, "id": str(case_id)},
    ).scalar_one()


# ── the registry actually runs on the Didox rail ─────────────────────────────


@requires_real_db
def test_the_didox_rail_spawns_both_registry_checks(sf) -> None:  # noqa: ANN001
    _didox_rail()
    with sf() as db:
        case_id = _submit(db)
        assert {"gov_registry", "vat_status"} <= set(_checks(db, case_id))


# ── the documents check waits for the registry verdict ───────────────────────


@requires_real_db
def test_the_documents_check_is_not_dispatched_before_the_registry_answers(sf) -> None:  # noqa: ANN001
    from app.tasks import verification as tasks  # noqa: PLC0415

    _didox_rail()
    with sf() as db:
        case_id = _submit(db)
        ids = {k: c.id for k, c in _checks(db, case_id).items()}

    first_wave: list[int] = []
    with patch.object(tasks, "_dispatch_single", first_wave.append):
        tasks.run_verification_checks.apply(args=[case_id]).get()

    assert ids["gov_registry"] in first_wave
    assert ids["documents_complete"] not in first_wave, (
        "documents_complete ran in parallel with the registry check it depends on"
    )


# ── the three outcomes ────────────────────────────────────────────────────────


@requires_real_db
def test_a_confirmed_company_needs_no_certificate(sf) -> None:  # noqa: ANN001
    from app.domains.verification.models import VerificationCase  # noqa: PLC0415
    from app.integrations import gov_registry  # noqa: PLC0415

    _didox_rail()
    with sf() as db:
        case_id = _submit(db)

    with patch.object(gov_registry, "get_gov_registry_client", lambda db: _Registry("active")):
        _run_pipeline(case_id)

    with sf() as db:
        checks = _checks(db, case_id)
        assert checks["gov_registry"].status.value == "passed"
        assert checks["documents_complete"].status.value == "passed"
        assert checks["documents_complete"].result["registry_passed"] is True
        assert db.get(VerificationCase, case_id).status.value == "pending_review"
        assert _needs_info_events(db, case_id) == 0, (
            "the applicant was told to upload a certificate that was then waived"
        )


@requires_real_db
def test_a_liquidated_company_still_needs_the_certificate(sf) -> None:  # noqa: ANN001
    from app.integrations import gov_registry  # noqa: PLC0415

    _didox_rail()
    with sf() as db:
        case_id = _submit(db)

    with patch.object(gov_registry, "get_gov_registry_client", lambda db: _Registry("liquidated")):
        _run_pipeline(case_id)

    with sf() as db:
        checks = _checks(db, case_id)
        assert checks["gov_registry"].status.value == "failed"
        assert checks["documents_complete"].status.value == "failed"
        assert checks["documents_complete"].result["missing"] == ["registration_certificate"]


@requires_real_db
def test_a_registry_that_is_down_falls_back_to_the_document_rule(sf) -> None:  # noqa: ANN001
    """The provider exhausts its retries; the documents check must still run —
    judged the old way — rather than wait forever for a verdict that never comes."""
    from app.domains.verification.models import VerificationCase  # noqa: PLC0415
    from app.integrations import gov_registry  # noqa: PLC0415

    _didox_rail()
    with sf() as db:
        case_id = _submit(db, with_certificate=True)

    with patch.object(gov_registry, "get_gov_registry_client", lambda db: _Registry(down=True)):
        _run_pipeline(case_id)

    with sf() as db:
        checks = _checks(db, case_id)
        assert checks["gov_registry"].status.value == "unavailable"
        assert checks["documents_complete"].status.value == "passed"
        assert checks["documents_complete"].result["registry_passed"] is False
        # Exhausted `unavailable` no longer blocks, so a human can still decide.
        assert db.get(VerificationCase, case_id).status.value == "pending_review"


class _FlakyRegistry(_Registry):
    """Down for the first `failures` calls of each lookup, then answers — the
    shape of the Didox test contour on 23.09.2026."""

    def __init__(self, failures: int) -> None:
        super().__init__("active")
        self.left = {"company": failures, "vat": failures}

    def lookup_company(self, inn: str):  # noqa: ANN201
        self.down = self.left["company"] > 0
        self.left["company"] -= 1
        return super().lookup_company(inn)

    def lookup_vat(self, inn: str):  # noqa: ANN201
        self.down = self.left["vat"] > 0
        self.left["vat"] -= 1
        return super().lookup_vat(inn)


@requires_real_db
def test_an_answer_after_a_timeout_clears_the_old_error(sf) -> None:  # noqa: ANN001
    """A check that got its answer on a retry must not still show the error of the
    attempt before it. It did: the portal showed «Последняя ошибка: no_snapshot»
    under a verdict that had been reached — the screen claimed both "answered" and
    "failed" at once."""
    from app.integrations import gov_registry  # noqa: PLC0415

    _didox_rail()
    with sf() as db:
        case_id = _submit(db)

    flaky = _FlakyRegistry(failures=1)
    with patch.object(gov_registry, "get_gov_registry_client", lambda db: flaky):
        _run_pipeline(case_id)

    with sf() as db:
        checks = _checks(db, case_id)
        for kind in ("gov_registry", "vat_status"):
            check = checks[kind]
            assert check.attempts == 2, f"{kind} should have needed one retry"
            assert check.status.value == "passed", kind
            assert check.last_error is None, (
                f"{kind} still reports {check.last_error!r} after it got an answer"
            )
