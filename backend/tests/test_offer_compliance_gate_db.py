"""
Compliance: licences, evaluation and the publish gate (P5 W3). Guarded real-DB.

The decision table lives in test_offer_compliance_verdicts.py. What is pinned
here is everything around it:

  * **A licence is per regime, and expiry is checked on read.** An `active` row
    with a past `expires_at` is an expired licence, not a valid one — the window
    a nightly sweep would leave open is exactly what this table exists to close.
  * **The gate holds an offer as a DRAFT rather than rejecting the request.**
    A `docs_required` substance can only get its documents after the offer row
    exists (files are uploaded to an offer id), so refusing creation would make
    such an offer impossible to publish at all. Held offers are never sent to
    moderation, and uploading the missing document promotes one.
  * **Re-evaluation happens on every edit (FR-C6)** and again at approval — a
    licence can expire between submitting and approving.
  * **Enforcement is a runtime setting that ships off.** With it off nothing is
    blocked, but the verdict is still stamped so staff can see what would be.
"""

from __future__ import annotations

import datetime
import decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller,
    make_seller_offer,
    make_staff,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

pytestmark = requires_real_db

_A = "/api/v1/admin"
_P = "/api/v1/portal"


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def db(engine: sa.Engine) -> Session:
    clean(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM substances"))
    session = session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _substance(db: Session, **kwargs):  # noqa: ANN003, ANN202
    from app.domains.compliance.models import Substance  # noqa: PLC0415
    from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

    row = Substance(
        code=kwargs.pop("code", "acetone"),
        name_ru=kwargs.pop("name_ru", "Ацетон"),
        hs_code=kwargs.pop("hs_code", "2914.11"),
        regulation_level=kwargs.pop("regulation_level", RegulationLevel.license_required),
        regulation_regime=kwargs.pop("regulation_regime", RegulationRegime.precursor_list_iv),
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def _verified_company(db: Session, phone: str = "+998900000101", tax_id: str = "301111111"):  # noqa: ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    # distributor+trader: publishes offers — the role gates (T-B) require it
    company = make_company(db, account, tax_id, roles=["distributor", "trader"])
    company.status = CompanyStatus.verified
    company.legal_name = f'ООО "{tax_id}"'
    db.flush()
    return account, company


def _attach(db: Session, offer, kind: str) -> None:  # noqa: ANN001
    from app.domains.marketplace.models import SellerOfferFile  # noqa: PLC0415
    from app.models.enums import OfferFileKind  # noqa: PLC0415

    db.add(
        SellerOfferFile(
            offer_id=offer.id, kind=OfferFileKind(kind), file_name=f"{kind}.pdf",
            mime_type="application/pdf", storage_path=f"offers/{offer.id}/{kind}.pdf",
        )
    )
    db.flush()


def _enforce(db: Session, on: bool) -> None:
    from app.services import settings_service  # noqa: PLC0415

    settings_service.set_many(db, {"dangerous_check_enforced": on}, None)
    db.flush()


class TestLicences:
    def test_register_creates_an_active_licence_and_audits(self, db: Session) -> None:
        from app.domains.compliance import licenses as svc  # noqa: PLC0415
        from app.models.enums import LicenseStatus, RegulationRegime  # noqa: PLC0415

        staff = make_staff(db)
        _, company = _verified_company(db)
        licence = svc.register(
            db,
            company_id=company.id,
            regime=RegulationRegime.precursor_list_iv,
            license_number="ЛИЦ-42",
            staff_user_id=staff.id,
        )
        assert licence.status == LicenseStatus.active
        actions = db.execute(
            sa.text("SELECT action FROM audit_log WHERE entity = 'company_licenses'")
        ).scalars().all()
        assert actions == ["license.register"]

    def test_active_for_matches_the_regime_only(self, db: Session) -> None:
        from app.domains.compliance import licenses as svc  # noqa: PLC0415
        from app.models.enums import RegulationRegime  # noqa: PLC0415

        staff = make_staff(db)
        _, company = _verified_company(db)
        svc.register(
            db, company_id=company.id, regime=RegulationRegime.pkm916_import,
            staff_user_id=staff.id,
        )
        assert svc.active_for(db, company.id, RegulationRegime.pkm916_import) is not None
        assert svc.active_for(db, company.id, RegulationRegime.precursor_list_iv) is None

    def test_an_expired_licence_is_not_active(self, db: Session) -> None:
        """`status='active'` with a past date is an expired licence nobody swept."""
        from app.domains.compliance import licenses as svc  # noqa: PLC0415
        from app.models.enums import RegulationRegime  # noqa: PLC0415

        staff = make_staff(db)
        _, company = _verified_company(db)
        svc.register(
            db,
            company_id=company.id,
            regime=RegulationRegime.precursor_list_iv,
            expires_at=datetime.date.today() - datetime.timedelta(days=1),
            staff_user_id=staff.id,
        )
        assert svc.active_for(db, company.id, RegulationRegime.precursor_list_iv) is None

    def test_a_licence_expiring_today_still_counts(self, db: Session) -> None:
        from app.domains.compliance import licenses as svc  # noqa: PLC0415
        from app.models.enums import RegulationRegime  # noqa: PLC0415

        staff = make_staff(db)
        _, company = _verified_company(db)
        svc.register(
            db,
            company_id=company.id,
            regime=RegulationRegime.precursor_list_iv,
            expires_at=datetime.date.today(),
            staff_user_id=staff.id,
        )
        assert svc.active_for(db, company.id, RegulationRegime.precursor_list_iv) is not None

    def test_revoking_takes_it_out_immediately(self, db: Session) -> None:
        from app.domains.compliance import licenses as svc  # noqa: PLC0415
        from app.models.enums import LicenseStatus, RegulationRegime  # noqa: PLC0415

        staff = make_staff(db)
        _, company = _verified_company(db)
        licence = svc.register(
            db, company_id=company.id, regime=RegulationRegime.precursor_list_iv,
            staff_user_id=staff.id,
        )
        svc.revoke(db, licence, reason="аннулирована органом", staff_user_id=staff.id)
        assert licence.status == LicenseStatus.revoked
        assert svc.active_for(db, company.id, RegulationRegime.precursor_list_iv) is None

    def test_category_must_match_when_the_substance_names_one(self, db: Session) -> None:
        """A licence for one category of a regime does not cover another."""
        from app.domains.compliance import licenses as svc  # noqa: PLC0415
        from app.models.enums import RegulationRegime  # noqa: PLC0415

        staff = make_staff(db)
        _, company = _verified_company(db)
        svc.register(
            db, company_id=company.id, regime=RegulationRegime.explosive_toxic,
            category="Ядовитые вещества", staff_user_id=staff.id,
        )
        assert (
            svc.active_for(
                db, company.id, RegulationRegime.explosive_toxic, category="Взрывчатые вещества"
            )
            is None
        )
        assert (
            svc.active_for(
                db, company.id, RegulationRegime.explosive_toxic, category=" ядовитые вещества "
            )
            is not None
        )


class TestEvaluate:
    def test_an_offer_without_chemistry_is_free(self, db: Session) -> None:
        """Telegram-origin offers carry no substance at all (webapp is frozen) —
        they must sail through untouched."""
        from app.domains.marketplace import compliance as svc  # noqa: PLC0415

        offer = make_seller_offer(db, seller=make_seller(db, 555))
        verdict = svc.evaluate(db, offer)
        assert verdict.ok is True
        assert verdict.substance_id is None

    def test_a_manually_typed_cas_resolves_to_the_registry(self, db: Session) -> None:
        """FR-C2 allows typing CAS/HS by hand; the gate must still see it."""
        from app.domains.marketplace import compliance as svc  # noqa: PLC0415

        substance = _substance(db, cas="67-64-1")
        _, company = _verified_company(db)
        offer = make_seller_offer(db, company=company, cas_number="67-64-1")
        verdict = svc.evaluate(db, offer)
        assert verdict.substance_id == substance.id
        assert verdict.ok is False

    def test_the_companys_licence_satisfies_the_offer(self, db: Session) -> None:
        from app.domains.compliance import licenses as company_license_service  # noqa: PLC0415
        from app.domains.marketplace import compliance as svc  # noqa: PLC0415
        from app.models.enums import RegulationRegime  # noqa: PLC0415

        staff = make_staff(db)
        substance = _substance(db)
        _, company = _verified_company(db)
        offer = make_seller_offer(db, company=company, substance_id=substance.id)
        assert svc.evaluate(db, offer).ok is False

        company_license_service.register(
            db, company_id=company.id, regime=RegulationRegime.precursor_list_iv,
            staff_user_id=staff.id,
        )
        assert svc.evaluate(db, offer).ok is True

    def test_a_telegram_seller_can_never_satisfy_a_licence(self, db: Session) -> None:
        """A TG seller has no portal company, so there is nobody to hold a
        licence — the offer stays blocked rather than passing by default."""
        from app.domains.marketplace import compliance as svc  # noqa: PLC0415

        substance = _substance(db)
        offer = make_seller_offer(db, seller=make_seller(db, 556), substance_id=substance.id)
        verdict = svc.evaluate(db, offer)
        assert verdict.ok is False

    def test_documents_are_counted_from_the_offers_files(self, db: Session) -> None:
        from app.domains.marketplace import compliance as svc  # noqa: PLC0415
        from app.models.enums import RegulationLevel, RegulationRegime  # noqa: PLC0415

        substance = _substance(
            db,
            code="plastic_waste",
            name_ru="Отходы пластмасс",
            hs_code="3915",
            regulation_level=RegulationLevel.docs_required,
            regulation_regime=RegulationRegime.pkm916_import,
            required_docs=["certificate"],
        )
        _, company = _verified_company(db)
        offer = make_seller_offer(db, company=company, substance_id=substance.id)
        assert svc.evaluate(db, offer).ok is False

        _attach(db, offer, "certificate")
        db.refresh(offer)
        assert svc.evaluate(db, offer).ok is True

    def test_stamp_caches_the_verdict_on_the_offer(self, db: Session) -> None:
        from app.domains.marketplace import compliance as svc  # noqa: PLC0415

        substance = _substance(db)
        _, company = _verified_company(db)
        offer = make_seller_offer(db, company=company, substance_id=substance.id)
        svc.evaluate_and_stamp(db, offer)
        assert offer.compliance_ok is False
        assert offer.compliance_level == substance.regulation_level
        assert offer.compliance_missing == [{"kind": "license", "detail": "precursor_list_iv"}]
        assert offer.compliance_checked_at is not None


class TestPublishGate:
    def test_off_by_default(self, db: Session) -> None:
        """`dangerous_check_enforced` ships off: turning it on before the legal
        review of the lists would block trade on an incomplete registry."""
        from app.services.settings_service import _SPECS  # noqa: PLC0415

        assert _SPECS["dangerous_check_enforced"].default is False

    def test_with_the_gate_off_a_blocked_offer_still_reaches_moderation(
        self, db: Session
    ) -> None:
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415

        substance = _substance(db)
        account, company = _verified_company(db)
        _enforce(db, False)
        offer = offer_service.create_company_offer(
            db, company, account,
            CompanyOfferIn(product_text="Ацетон техн.", substance_id=substance.id),
        )
        assert offer.status == SellerOfferStatus.pending_moderation
        # …but the verdict is recorded, so staff can see what would be blocked.
        assert offer.compliance_ok is False

    def test_with_the_gate_on_the_offer_is_held_as_a_draft(self, db: Session) -> None:
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415

        substance = _substance(db)
        account, company = _verified_company(db)
        _enforce(db, True)
        offer = offer_service.create_company_offer(
            db, company, account,
            CompanyOfferIn(product_text="Ацетон техн.", substance_id=substance.id),
        )
        assert offer.status == SellerOfferStatus.draft, (
            "a held offer must not enter the moderation queue"
        )
        assert offer.compliance_ok is False

    def test_a_compliant_offer_is_unaffected(self, db: Session) -> None:
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.compliance import licenses as company_license_service  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import RegulationRegime, SellerOfferStatus  # noqa: PLC0415

        staff = make_staff(db)
        substance = _substance(db)
        account, company = _verified_company(db)
        company_license_service.register(
            db, company_id=company.id, regime=RegulationRegime.precursor_list_iv,
            staff_user_id=staff.id,
        )
        _enforce(db, True)
        offer = offer_service.create_company_offer(
            db, company, account,
            CompanyOfferIn(product_text="Ацетон техн.", substance_id=substance.id),
        )
        assert offer.status == SellerOfferStatus.pending_moderation

    def test_a_low_concentration_publishes_without_a_licence(self, db: Session) -> None:
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415

        substance = _substance(db, threshold_concentration_pct=decimal.Decimal("60"))
        account, company = _verified_company(db)
        _enforce(db, True)
        offer = offer_service.create_company_offer(
            db, company, account,
            CompanyOfferIn(
                product_text="Ацетон 20%",
                substance_id=substance.id,
                declared_concentration_pct=decimal.Decimal("20"),
            ),
        )
        assert offer.status == SellerOfferStatus.pending_moderation
        assert offer.compliance_ok is True

    def test_editing_re_evaluates(self, db: Session) -> None:
        """FR-C6: a live offer edited into a regulated substance is pulled back."""
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415

        substance = _substance(db)
        account, company = _verified_company(db)
        _enforce(db, True)
        offer = offer_service.create_company_offer(
            db, company, account, CompanyOfferIn(product_text="ПП гранулы")
        )
        assert offer.status == SellerOfferStatus.pending_moderation
        offer.status = SellerOfferStatus.approved
        db.flush()

        offer_service.update_company_offer(
            db, offer,
            CompanyOfferIn(product_text="Ацетон техн.", substance_id=substance.id),
        )
        assert offer.status == SellerOfferStatus.draft
        assert offer.published_at is None

    def test_attaching_the_missing_document_releases_the_draft(self, db: Session) -> None:
        """A docs_required offer can only get its documents once it exists, so
        the upload path is what promotes it into the queue."""
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import (  # noqa: PLC0415
            RegulationLevel,
            RegulationRegime,
            SellerOfferStatus,
        )

        substance = _substance(
            db,
            code="plastic_waste",
            name_ru="Отходы пластмасс",
            hs_code="3915",
            regulation_level=RegulationLevel.docs_required,
            regulation_regime=RegulationRegime.pkm916_import,
            required_docs=["certificate"],
        )
        account, company = _verified_company(db)
        _enforce(db, True)
        offer = offer_service.create_company_offer(
            db, company, account,
            CompanyOfferIn(product_text="Скрап ПЭТ", substance_id=substance.id),
        )
        assert offer.status == SellerOfferStatus.draft

        _attach(db, offer, "certificate")
        db.refresh(offer)
        released = offer_service.recheck_compliance_after_files(db, offer)
        assert released is True
        assert offer.status == SellerOfferStatus.pending_moderation

    def test_registering_the_licence_releases_the_draft_on_the_next_save(
        self, db: Session
    ) -> None:
        """The other half of the demo. A licence lives on the COMPANY, so a held
        offer cannot be fixed by attaching anything to it — re-saving is the
        seller's only move, and it has to work or the offer is stuck forever."""
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.compliance import licenses as company_license_service  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import RegulationRegime, SellerOfferStatus  # noqa: PLC0415

        staff = make_staff(db)
        substance = _substance(db)
        account, company = _verified_company(db)
        _enforce(db, True)
        payload = CompanyOfferIn(product_text="Ацетон техн.", substance_id=substance.id)
        offer = offer_service.create_company_offer(db, company, account, payload)
        assert offer.status == SellerOfferStatus.draft

        company_license_service.register(
            db, company_id=company.id, regime=RegulationRegime.precursor_list_iv,
            staff_user_id=staff.id,
        )
        offer, requeued = offer_service.update_company_offer(db, offer, payload)
        assert offer.status == SellerOfferStatus.pending_moderation
        assert requeued is True, "the team has to be told there is something to moderate"

    def test_turning_the_gate_off_releases_held_drafts_on_the_next_save(
        self, db: Session
    ) -> None:
        """An operator switching enforcement off must not leave offers stranded."""
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415

        substance = _substance(db)
        account, company = _verified_company(db)
        _enforce(db, True)
        payload = CompanyOfferIn(product_text="Ацетон техн.", substance_id=substance.id)
        offer = offer_service.create_company_offer(db, company, account, payload)
        assert offer.status == SellerOfferStatus.draft

        _enforce(db, False)
        offer, _ = offer_service.update_company_offer(db, offer, payload)
        assert offer.status == SellerOfferStatus.pending_moderation

    def test_a_prohibited_substance_is_never_released(self, db: Session) -> None:
        from app.domains.companies.schemas import CompanyOfferIn  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import (  # noqa: PLC0415
            RegulationLevel,
            RegulationRegime,
            SellerOfferStatus,
        )

        substance = _substance(
            db,
            code="ddt",
            name_ru="ДДТ",
            hs_code="2903.92",
            regulation_level=RegulationLevel.prohibited,
            regulation_regime=RegulationRegime.pkm916_import,
            source_act="ПКМ №916",
        )
        account, company = _verified_company(db)
        _enforce(db, True)
        offer = offer_service.create_company_offer(
            db, company, account, CompanyOfferIn(product_text="ДДТ", substance_id=substance.id)
        )
        assert offer.status == SellerOfferStatus.draft
        _attach(db, offer, "certificate")
        _attach(db, offer, "sds")
        db.refresh(offer)
        assert offer_service.recheck_compliance_after_files(db, offer) is False
        assert offer.status == SellerOfferStatus.draft

    def test_moderation_refuses_to_approve_a_blocked_offer(self, db: Session) -> None:
        """A licence can expire between submission and approval."""
        from app.domains.marketplace import compliance as offer_compliance_service  # noqa: PLC0415
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415

        staff = make_staff(db)
        substance = _substance(db)
        _, company = _verified_company(db)
        offer = make_seller_offer(
            db,
            company=company,
            substance_id=substance.id,
            status=SellerOfferStatus.pending_moderation,
        )
        _enforce(db, True)
        with pytest.raises(offer_compliance_service.CompliancePublishBlocked):
            offer_service.moderate_offer(db, offer, staff.id, approve=True)

    def test_moderation_may_still_reject_a_blocked_offer(self, db: Session) -> None:
        from app.domains.marketplace import service as offer_service  # noqa: PLC0415
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415

        staff = make_staff(db)
        substance = _substance(db)
        _, company = _verified_company(db)
        offer = make_seller_offer(
            db,
            company=company,
            substance_id=substance.id,
            status=SellerOfferStatus.pending_moderation,
        )
        _enforce(db, True)
        offer_service.moderate_offer(db, offer, staff.id, approve=False, note="нельзя")
        assert offer.status == SellerOfferStatus.rejected


# ── API surface ───────────────────────────────────────────────────────────────


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM substances"))
    session = session_factory(engine)
    fake_redis = FakeRedis()
    app = create_app()

    def _override_db():  # noqa: ANN202
        session_ = session()
        try:
            yield session_
        finally:
            session_.close()

    def _override_redis():  # noqa: ANN202
        yield fake_redis

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(app) as client:
        yield client, session
    clean(engine)


def _staff_headers(session, role="admin", email="admin@example.com"):  # noqa: ANN001, ANN202
    from app.core.security import create_access_token  # noqa: PLC0415
    from app.models.enums import StaffRole  # noqa: PLC0415

    with session() as db:
        staff = make_staff(db, email)
        staff.role = StaffRole(role)
        db.commit()
        staff_id = staff.id
    return {"Authorization": f"Bearer {create_access_token(subject=str(staff_id), role=role)}"}


def _scene(session):  # noqa: ANN001, ANN202
    """A verified company with a blocked (licence-required) offer awaiting moderation."""
    from app.core.security import create_portal_access_token  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    with session() as db:
        substance = _substance(db)
        account, company = _verified_company(db)
        offer = make_seller_offer(
            db,
            company=company,
            substance_id=substance.id,
            status=SellerOfferStatus.pending_moderation,
        )
        # Stamp the verdict the way a real create/edit would — a raw insert
        # bypasses the gate, and the cached fields are what the payload carries.
        from app.domains.marketplace import compliance as offer_compliance_service  # noqa: PLC0415

        offer_compliance_service.evaluate_and_stamp(db, offer)
        db.commit()
        return {
            "company_id": company.id,
            "offer_id": offer.id,
            "substance_id": substance.id,
            "headers": {
                "Authorization": f"Bearer {create_portal_access_token(subject=str(account.id))}"
            },
        }


class TestApi:
    def test_admin_registers_and_revokes_a_licence(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        headers = _staff_headers(session)

        created = client.post(
            f"{_A}/companies/{scene['company_id']}/licenses",
            json={"regime": "precursor_list_iv", "license_number": "ЛИЦ-42"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        licence_id = created.json()["id"]
        assert created.json()["is_active"] is True

        revoked = client.post(
            f"{_A}/licenses/{licence_id}/revoke",
            json={"reason": "аннулирована"},
            headers=headers,
        )
        assert revoked.status_code == 200
        assert revoked.json()["is_active"] is False

    def test_analyst_may_read_licences_but_not_register_them(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        analyst = _staff_headers(session, "analyst", "analyst@example.com")

        assert (
            client.get(f"{_A}/companies/{scene['company_id']}/licenses", headers=analyst).status_code
            == 200
        )
        assert (
            client.post(
                f"{_A}/companies/{scene['company_id']}/licenses",
                json={"regime": "precursor_list_iv"},
                headers=analyst,
            ).status_code
            == 403
        )

    def test_the_seller_sees_what_is_missing(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)

        got = client.get(
            f"{_P}/companies/{scene['company_id']}/offers/{scene['offer_id']}/compliance",
            headers=scene["headers"],
        )
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["ok"] is False
        assert body["level"] == "license_required"
        assert body["missing"] == [{"kind": "license", "detail": "precursor_list_iv"}]
        assert body["substance"]["code"] == "acetone"

    def test_the_offer_list_carries_the_substance_and_verdict(self, api) -> None:  # noqa: ANN001
        """The seller's own screens name what was picked instead of echoing a
        CAS back, and the cached verdict is why a held offer is a draft."""
        client, session = api
        scene = _scene(session)

        listed = client.get(
            f"{_P}/companies/{scene['company_id']}/offers", headers=scene["headers"]
        )
        assert listed.status_code == 200
        card = listed.json()[0]
        assert card["substance"]["name_ru"] == "Ацетон"
        assert card["compliance_ok"] is False
        assert card["compliance_missing"] == [
            {"kind": "license", "detail": "precursor_list_iv"}
        ]

    def test_the_seller_sees_their_own_licences(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        client.post(
            f"{_A}/companies/{scene['company_id']}/licenses",
            json={"regime": "precursor_list_iv", "license_number": "ЛИЦ-42"},
            headers=_staff_headers(session),
        )

        mine = client.get(
            f"{_P}/companies/{scene['company_id']}/licenses", headers=scene["headers"]
        )
        assert mine.status_code == 200
        assert [row["regime"] for row in mine.json()] == ["precursor_list_iv"]

    def test_another_company_cannot_read_the_compliance_of_this_offer(self, api) -> None:  # noqa: ANN001
        from app.core.security import create_portal_access_token  # noqa: PLC0415

        client, session = api
        scene = _scene(session)
        with session() as db:
            stranger = make_account(db, "+998900000999")
            db.commit()
            stranger_headers = {
                "Authorization": f"Bearer {create_portal_access_token(subject=str(stranger.id))}"
            }

        got = client.get(
            f"{_P}/companies/{scene['company_id']}/offers/{scene['offer_id']}/compliance",
            headers=stranger_headers,
        )
        assert got.status_code == 404

    def test_moderation_sees_the_compliance_block(self, api) -> None:  # noqa: ANN001
        """FR-C5 — the moderator decides with the substance in front of them."""
        client, session = api
        _scene(session)
        headers = _staff_headers(session)

        queue = client.get(f"{_A}/moderation/offers", headers=headers)
        assert queue.status_code == 200
        card = queue.json()[0]
        assert card["compliance"]["level"] == "license_required"
        assert card["compliance"]["ok"] is False
        assert card["compliance"]["substance"]["name_ru"] == "Ацетон"

    def test_approving_a_blocked_offer_is_a_409(self, api) -> None:  # noqa: ANN001
        client, session = api
        scene = _scene(session)
        headers = _staff_headers(session)
        with session() as db:
            _enforce(db, True)
            db.commit()

        blocked = client.post(
            f"{_A}/moderation/offers/{scene['offer_id']}/approve", json={}, headers=headers
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "compliance_blocked"
        assert blocked.json()["detail"]["missing"] == [
            {"kind": "license", "detail": "precursor_list_iv"}
        ]

        # …and it publishes once the licence exists.
        client.post(
            f"{_A}/companies/{scene['company_id']}/licenses",
            json={"regime": "precursor_list_iv"},
            headers=headers,
        )
        approved = client.post(
            f"{_A}/moderation/offers/{scene['offer_id']}/approve", json={}, headers=headers
        )
        assert approved.status_code == 200
