"""Registry-snapshot service (R6 / P7.c — T4.3). Guarded (test_polymer).

The service exists to keep one property true: **a snapshot row is written once
and never edited**. Everything else here follows from that — `latest()` reads the
newest row rather than a mutable "current" one, and re-checking a company adds
history instead of replacing it.

The other property under test is the degradation invariant R1 established and
INTEGRATIONS.md restates: a registry we cannot reach produces `None`, not an
exception and not an empty snapshot. An empty snapshot would read as "no such
company" — a finding about a real business, caused by us lacking an integration.
"""

from __future__ import annotations

import datetime

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_staff,
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


def _company(db):  # noqa: ANN001, ANN202
    account = make_account(db, "+998900000001")
    company = make_company(db, account, tax_id="301234567")
    db.flush()
    return company


def _snapshot_payload():  # noqa: ANN202
    from app.integrations.gov_registry import CompanySnapshot  # noqa: PLC0415

    return CompanySnapshot(
        inn="301234567",
        name='ООО "ПОЛИМЕР ТРЕЙД"',
        status="active",
        raw_status="ДЕЙСТВУЮЩЕЕ",
        director="Иванов И.И.",
    ).as_payload()


# ── recording ─────────────────────────────────────────────────────────────────


@requires_real_db
def test_a_manual_snapshot_carries_its_author(sf) -> None:  # noqa: ANN001
    from app.domains.verification import registry as registry_service  # noqa: PLC0415
    from app.domains.verification.registry_models import SNAPSHOT_SOURCE_MANUAL  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        staff = make_staff(db)
        snapshot = registry_service.record_snapshot(
            db,
            company,
            kind="company",
            source=SNAPSHOT_SOURCE_MANUAL,
            provider="manual",
            payload=_snapshot_payload(),
            note="проверено на registr.stat.uz",
            created_by=staff.id,
        )
        db.commit()

        assert snapshot.source == SNAPSHOT_SOURCE_MANUAL
        assert snapshot.created_by == staff.id
        assert snapshot.fetched_at is not None
        assert snapshot.payload["status"] == "active"


@requires_real_db
def test_an_automatic_snapshot_has_no_author(sf) -> None:  # noqa: ANN001
    """Nobody asserted it — the registry did."""
    from app.domains.verification import registry as registry_service  # noqa: PLC0415
    from app.domains.verification.registry_models import SNAPSHOT_SOURCE_REGISTRY  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        snapshot = registry_service.record_snapshot(
            db, company, kind="company", source=SNAPSHOT_SOURCE_REGISTRY,
            provider="pcd", payload=_snapshot_payload(),
        )
        db.commit()
        assert snapshot.created_by is None


@requires_real_db
def test_recording_is_audited_in_the_same_transaction(sf) -> None:  # noqa: ANN001
    from app.domains.verification import registry as registry_service  # noqa: PLC0415
    from app.models.staff import AuditLog  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        staff = make_staff(db)
        registry_service.record_snapshot(
            db, company, kind="vat", source="manual", provider="manual",
            payload={"registered": True}, created_by=staff.id,
        )
        db.commit()

        entry = db.query(AuditLog).filter(AuditLog.action == "registry.snapshot").one()
        assert entry.entity == "registry_snapshots"
        assert entry.details["kind"] == "vat"


@requires_real_db
def test_an_unknown_kind_is_refused_before_the_database_sees_it(sf) -> None:  # noqa: ANN001
    """The CHECK is the backstop; the typed error is the message an operator reads."""
    from app.domains.verification import registry as registry_service  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        with pytest.raises(registry_service.UnknownSnapshotKind):
            registry_service.record_snapshot(
                db, company, kind="horoscope", source="manual",
                provider="manual", payload={},
            )


@requires_real_db
def test_an_unknown_source_is_refused(sf) -> None:  # noqa: ANN001
    from app.domains.verification import registry as registry_service  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        with pytest.raises(registry_service.UnknownSnapshotSource):
            registry_service.record_snapshot(
                db, company, kind="company", source="vibes",
                provider="manual", payload={},
            )


@requires_real_db
def test_a_caller_supplied_observation_time_is_kept(sf) -> None:  # noqa: ANN001
    """An operator may transcribe a page they read yesterday; `fetched_at` is
    when the observation happened, `created_at` is when we wrote it down."""
    from app.domains.verification import registry as registry_service  # noqa: PLC0415

    observed = datetime.datetime(2026, 7, 1, 9, 30, tzinfo=datetime.UTC)
    with sf() as db:
        company = _company(db)
        snapshot = registry_service.record_snapshot(
            db, company, kind="company", source="manual", provider="manual",
            payload=_snapshot_payload(), fetched_at=observed,
        )
        db.commit()
        assert snapshot.fetched_at == observed
        assert snapshot.created_at != observed


# ── history, not state ────────────────────────────────────────────────────────


@requires_real_db
def test_re_checking_appends_history_and_latest_wins(sf) -> None:  # noqa: ANN001
    from app.domains.verification import registry as registry_service  # noqa: PLC0415
    from app.domains.verification.registry_models import RegistrySnapshot  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        registry_service.record_snapshot(
            db, company, kind="company", source="manual", provider="manual",
            payload={"inn": "301234567", "status": "active"},
        )
        db.commit()
        registry_service.record_snapshot(
            db, company, kind="company", source="manual", provider="manual",
            payload={"inn": "301234567", "status": "liquidated"},
        )
        db.commit()

        assert db.query(RegistrySnapshot).count() == 2, "a re-check is a new row"
        latest = registry_service.latest(db, company.id, "company")
        assert latest is not None
        assert latest.payload["status"] == "liquidated"


@requires_real_db
def test_latest_is_per_kind(sf) -> None:  # noqa: ANN001
    from app.domains.verification import registry as registry_service  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        registry_service.record_snapshot(
            db, company, kind="company", source="manual", provider="manual",
            payload={"inn": "301234567", "status": "active"},
        )
        registry_service.record_snapshot(
            db, company, kind="vat", source="manual", provider="manual",
            payload={"registered": False},
        )
        db.commit()

        assert registry_service.latest(db, company.id, "company").payload["status"] == "active"
        assert registry_service.latest(db, company.id, "vat").payload["registered"] is False
        assert registry_service.latest(db, company.id, "licenses") is None


@requires_real_db
def test_latest_for_a_company_with_nothing_recorded_is_none(sf) -> None:  # noqa: ANN001
    from app.domains.verification import registry as registry_service  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        db.commit()
        assert registry_service.latest(db, company.id, "company") is None


# ── the live path degrades ────────────────────────────────────────────────────


@requires_real_db
def test_an_unreachable_registry_records_nothing_and_does_not_raise(sf) -> None:  # noqa: ANN001
    """The R1 invariant: provider unavailability never blocks the manual path."""
    from app.domains.verification import registry as registry_service  # noqa: PLC0415
    from app.domains.verification.registry_models import RegistrySnapshot  # noqa: PLC0415

    with sf() as db:
        company = _company(db)
        db.commit()

        # `gov_registry_mode` ships `stub`, whose lookups all raise.
        assert registry_service.fetch_and_record(db, company, "company") is None
        db.commit()
        assert db.query(RegistrySnapshot).count() == 0


@requires_real_db
def test_a_reachable_registry_is_recorded_as_source_registry(sf) -> None:  # noqa: ANN001
    from unittest.mock import patch  # noqa: PLC0415

    from app.domains.verification import registry as registry_service  # noqa: PLC0415
    from app.integrations.gov_registry import CompanySnapshot  # noqa: PLC0415

    class _Live:
        def lookup_company(self, inn: str) -> CompanySnapshot:
            return CompanySnapshot(inn=inn, name="OOO REAL", status="active", raw_status="ACTIVE")

        def lookup_licenses(self, inn: str):  # noqa: ANN202
            return []

        def lookup_vat(self, inn: str):  # noqa: ANN202
            raise AssertionError("not asked")

    with sf() as db:
        company = _company(db)
        db.commit()
        with patch(
            "app.integrations.gov_registry.get_gov_registry_client", return_value=_Live()
        ):
            snapshot = registry_service.fetch_and_record(db, company, "company")
        db.commit()

        assert snapshot is not None
        assert snapshot.source == "registry"
        assert snapshot.created_by is None
        assert snapshot.payload["name"] == "OOO REAL"
        assert snapshot.raw_status == "ACTIVE"


@requires_real_db
def test_the_licences_lookup_records_a_list(sf) -> None:  # noqa: ANN001
    from unittest.mock import patch  # noqa: PLC0415

    from app.domains.verification import registry as registry_service  # noqa: PLC0415
    from app.integrations.gov_registry import LicenseSnapshot  # noqa: PLC0415

    class _Live:
        def lookup_company(self, inn: str):  # noqa: ANN202
            raise AssertionError("not asked")

        def lookup_licenses(self, inn: str) -> list[LicenseSnapshot]:
            return [LicenseSnapshot(regime="precursor_list_iv", number="AA-1")]

        def lookup_vat(self, inn: str):  # noqa: ANN202
            raise AssertionError("not asked")

    with sf() as db:
        company = _company(db)
        db.commit()
        with patch(
            "app.integrations.gov_registry.get_gov_registry_client", return_value=_Live()
        ):
            snapshot = registry_service.fetch_and_record(db, company, "licenses")
        db.commit()

        assert snapshot is not None
        assert snapshot.payload["licenses"][0]["number"] == "AA-1"
