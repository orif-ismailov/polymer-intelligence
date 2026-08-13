"""
Lab orders end to end against a real Postgres (P6 W2 — T2.1/T2.2).

The state machine itself is pinned by `test_lab_service.py` (a table, no
database). What needs a database is everything the machine touches when it
moves: the number sequence, the passport landing in the right place, the flag
that must be set by exactly one caller, the bell, and the audit trail.

The distinction this file exists to protect: **uploading a PDF is not the same
as having material analysed.** A seller can attach a passport and earn the
"lab passport" badge; only an order finishing through `complete_with_result`
sets `lab_verified`, and only that document is un-deletable.

Run with a localhost test_polymer DB; skipped otherwise (see _verification_db).
"""

from __future__ import annotations

import hashlib

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller_offer,
    make_staff,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

pytestmark = requires_real_db

_PDF = b"%PDF-1.4 laboratory passport"
_JPEG = b"\xff\xd8\xff\xe0 not a document"


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def db(engine: sa.Engine) -> Session:
    clean(engine)
    session = session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def stub_s3(monkeypatch) -> None:  # noqa: ANN001
    """No socket in tests: keep the validation, skip the bucket."""
    from app.domains.marketplace.models import SellerOfferFile  # noqa: PLC0415
    from app.services import storage_service  # noqa: PLC0415

    def fake_offer_upload(db, offer_id, content, filename, kind):  # noqa: ANN001, ANN202
        mime = storage_service.validate_upload(content, filename)
        row = SellerOfferFile(
            offer_id=offer_id,
            kind=kind,
            file_name=filename,
            mime_type=mime,
            size_bytes=len(content),
            storage_path=f"offers/{offer_id}/x-{filename}",
        )
        db.add(row)
        db.flush()
        return row

    def fake_deal_store(deal_id, section, content, filename):  # noqa: ANN001, ANN202
        mime = storage_service.validate_upload(content, filename)
        return (
            f"deals/{deal_id}/{section}/x-{filename}",
            mime,
            hashlib.sha256(content).hexdigest(),
        )

    monkeypatch.setattr(storage_service, "upload_offer_file", fake_offer_upload)
    monkeypatch.setattr(storage_service, "store_deal_file", fake_deal_store)


def _scene(db: Session):  # noqa: ANN202
    """A seller company with an approved offer, plus a staff operator."""
    owner = make_account(db, "+998900000201")
    company = make_company(db, owner, tax_id="300000201")
    offer = make_seller_offer(db, company=company, product_text="PP H030")
    staff = make_staff(db, email="lab-op@example.com")
    db.flush()
    return company, owner, offer, staff


class TestCreateOrder:
    def test_an_order_gets_a_number_and_lands_submitted(self, db: Session) -> None:
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, _staff = _scene(db)
        order = lab_service.create_order(
            db, company=company, account=owner, offer=offer, sample_volume="2 kg"
        )
        assert order.status == LabOrderStatus.submitted
        assert order.number.startswith("LAB-")
        assert order.number.count("-") == 2

    def test_numbers_do_not_repeat(self, db: Session) -> None:
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, _staff = _scene(db)
        numbers = {
            lab_service.create_order(db, company=company, account=owner, offer=offer).number
            for _ in range(3)
        }
        assert len(numbers) == 3

    def test_an_order_about_nothing_is_refused_before_the_database(
        self, db: Session
    ) -> None:
        from app.services import lab_service  # noqa: PLC0415

        company, owner, _offer, _staff = _scene(db)
        with pytest.raises(lab_service.LabOrderTargetMissing):
            lab_service.create_order(db, company=company, account=owner)

    def test_a_company_cannot_order_an_analysis_of_someone_elses_offer(
        self, db: Session
    ) -> None:
        from app.services import lab_service  # noqa: PLC0415

        _company, _owner, offer, _staff = _scene(db)
        outsider_owner = make_account(db, "+998900000202")
        outsider = make_company(db, outsider_owner, tax_id="300000202")
        with pytest.raises(lab_service.LabOrderNotAllowed):
            lab_service.create_order(
                db, company=outsider, account=outsider_owner, offer=offer
            )

    def test_the_submission_is_journalled_for_the_staff_card(self, db: Session) -> None:
        from app.models.events import DomainEvent  # noqa: PLC0415
        from app.services import event_types, lab_service  # noqa: PLC0415

        company, owner, offer, _staff = _scene(db)
        order = lab_service.create_order(db, company=company, account=owner, offer=offer)
        db.flush()
        events = (
            db.query(DomainEvent)
            .filter(DomainEvent.event_type == event_types.LAB_ORDER_SUBMITTED)
            .all()
        )
        assert [e.aggregate_id for e in events] == [str(order.id)]
        assert events[0].payload["number"] == order.number


class TestTransitions:
    def _submitted(self, db: Session):  # noqa: ANN202
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, staff = _scene(db)
        order = lab_service.create_order(db, company=company, account=owner, offer=offer)
        return order, staff, company

    def test_the_operator_walks_it_forward(self, db: Session) -> None:
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, staff, _company = self._submitted(db)
        for target in (
            LabOrderStatus.accepted,
            LabOrderStatus.sample_awaited,
            LabOrderStatus.in_analysis,
        ):
            lab_service.transition(db, order, target, staff_user=staff)
            assert order.status == target
        assert order.handled_by == staff.id

    def test_skipping_a_step_is_refused(self, db: Session) -> None:
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, staff, _company = self._submitted(db)
        with pytest.raises(lab_service.InvalidLabTransition):
            lab_service.transition(
                db, order, LabOrderStatus.in_analysis, staff_user=staff
            )

    def test_done_cannot_be_set_by_hand(self, db: Session) -> None:
        """It needs the passport. A typed error beats the IntegrityError the
        schema CHECK would otherwise raise in the operator's face."""
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, staff, _company = self._submitted(db)
        lab_service.transition(db, order, LabOrderStatus.accepted, staff_user=staff)
        lab_service.transition(db, order, LabOrderStatus.sample_awaited, staff_user=staff)
        lab_service.transition(db, order, LabOrderStatus.in_analysis, staff_user=staff)
        with pytest.raises(lab_service.LabResultRequired):
            lab_service.transition(db, order, LabOrderStatus.done, staff_user=staff)

    def test_rejecting_without_a_reason_is_refused(self, db: Session) -> None:
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, staff, _company = self._submitted(db)
        with pytest.raises(lab_service.ReasonRequired):
            lab_service.transition(db, order, LabOrderStatus.rejected, staff_user=staff)

        lab_service.transition(
            db, order, LabOrderStatus.rejected, staff_user=staff, note="лаборатория занята"
        )
        assert order.status == LabOrderStatus.rejected
        assert order.rejected_reason == "лаборатория занята"

    def test_a_finished_order_does_not_move_again(self, db: Session) -> None:
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, staff, _company = self._submitted(db)
        lab_service.transition(
            db, order, LabOrderStatus.rejected, staff_user=staff, note="нет реагента"
        )
        with pytest.raises(lab_service.InvalidLabTransition):
            lab_service.transition(db, order, LabOrderStatus.accepted, staff_user=staff)

    def test_each_step_rings_the_customers_bell(self, db: Session) -> None:
        """dedup=False: two steps on one order are two different sentences."""
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.models.notifications import PortalNotification  # noqa: PLC0415
        from app.services import lab_service, notification_service  # noqa: PLC0415

        order, staff, _company = self._submitted(db)
        lab_service.transition(db, order, LabOrderStatus.accepted, staff_user=staff)
        lab_service.transition(db, order, LabOrderStatus.sample_awaited, staff_user=staff)
        db.flush()

        rows = (
            db.query(PortalNotification)
            .filter(
                PortalNotification.kind == notification_service.KIND_LAB_ORDER_STATUS
            )
            .all()
        )
        assert len(rows) == 2
        assert {r.params["status"] for r in rows} == {"accepted", "sample_awaited"}
        assert rows[0].entity == "lab_order"


class TestCompleteWithResult:
    def _ready(self, db: Session):  # noqa: ANN202
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, staff = _scene(db)
        order = lab_service.create_order(db, company=company, account=owner, offer=offer)
        for target in (
            LabOrderStatus.accepted,
            LabOrderStatus.sample_awaited,
            LabOrderStatus.in_analysis,
        ):
            lab_service.transition(db, order, target, staff_user=staff)
        return order, offer, staff

    def test_the_passport_lands_on_the_offer_and_verifies_it(
        self, db: Session, stub_s3: None
    ) -> None:
        from app.models.enums import LabOrderStatus, OfferFileKind  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, offer, staff = self._ready(db)
        lab_service.complete_with_result(
            db, order, staff_user=staff, content=_PDF, filename="passport.pdf"
        )
        db.flush()
        db.refresh(offer)

        assert order.status == LabOrderStatus.done
        assert order.completed_at is not None
        assert order.result_offer_file_id is not None
        assert offer.lab_verified is True
        assert [f.kind for f in offer.files] == [OfferFileKind.lab_passport]

    def test_a_non_pdf_is_refused_before_anything_is_stored(
        self, db: Session, stub_s3: None
    ) -> None:
        """A JPEG passes the generic allow-list; it is not a laboratory passport."""
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, offer, staff = self._ready(db)
        with pytest.raises(lab_service.InvalidResultFile):
            lab_service.complete_with_result(
                db, order, staff_user=staff, content=_JPEG, filename="scan.jpg"
            )
        db.flush()
        db.refresh(offer)
        assert order.status == LabOrderStatus.in_analysis
        assert offer.files == []
        assert offer.lab_verified is False

    def test_it_cannot_finish_an_order_that_is_not_being_analysed(
        self, db: Session, stub_s3: None
    ) -> None:
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, staff = _scene(db)
        order = lab_service.create_order(db, company=company, account=owner, offer=offer)
        with pytest.raises(lab_service.InvalidLabTransition):
            lab_service.complete_with_result(
                db, order, staff_user=staff, content=_PDF, filename="p.pdf"
            )

    def test_completing_does_not_send_a_live_offer_back_to_moderation(
        self, db: Session, stub_s3: None
    ) -> None:
        """Staff produced this document and have seen it. Re-queueing would
        un-publish a live offer as a reward for finishing the analysis — unlike a
        SELLER uploading a passport, which does re-enter the queue."""
        from app.models.enums import SellerOfferStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, offer, staff = self._ready(db)
        assert offer.status == SellerOfferStatus.approved
        lab_service.complete_with_result(
            db, order, staff_user=staff, content=_PDF, filename="passport.pdf"
        )
        db.flush()
        db.refresh(offer)
        assert offer.status == SellerOfferStatus.approved

    def test_the_completion_is_journalled(self, db: Session, stub_s3: None) -> None:
        from app.models.events import DomainEvent  # noqa: PLC0415
        from app.services import event_types, lab_service  # noqa: PLC0415

        order, _offer, staff = self._ready(db)
        lab_service.complete_with_result(
            db, order, staff_user=staff, content=_PDF, filename="passport.pdf"
        )
        db.flush()
        assert (
            db.query(DomainEvent)
            .filter(DomainEvent.event_type == event_types.LAB_ORDER_COMPLETED)
            .count()
            == 1
        )


class TestDealSideResult:
    """An order raised from the Trade Room puts its passport into the deal.

    It goes through `deal_service.add_document` rather than writing
    `deal_documents` by hand: that is the deals context's own door, so the
    document arrives with that context's event and both parties' bells, and this
    module does not reach into a domain it does not own.
    """

    def _deal_order(self, db: Session):  # noqa: ANN202
        from app.models.deals import Deal  # noqa: PLC0415
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        buyer_owner = make_account(db, "+998900000211")
        seller_owner = make_account(db, "+998900000212")
        buyer = make_company(db, buyer_owner, tax_id="300000211")
        seller = make_company(db, seller_owner, tax_id="300000212")
        staff = make_staff(db, email="lab-deal@example.com")
        deal = Deal(
            number="DEAL-2026-000900",
            buyer_company_id=buyer.id,
            seller_company_id=seller.id,
            created_by_user_account_id=buyer_owner.id,
        )
        db.add(deal)
        db.flush()

        order = lab_service.create_order(
            db, company=buyer, account=buyer_owner, deal=deal, comment="проверить MFI"
        )
        for target in (
            LabOrderStatus.accepted,
            LabOrderStatus.sample_awaited,
            LabOrderStatus.in_analysis,
        ):
            lab_service.transition(db, order, target, staff_user=staff)
        return order, deal, buyer, staff

    def test_the_passport_lands_in_the_trade_room(
        self, db: Session, stub_s3: None
    ) -> None:
        from app.models.deals import DealDocument  # noqa: PLC0415
        from app.models.enums import DealDocumentKind, LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, deal, buyer, staff = self._deal_order(db)
        lab_service.complete_with_result(
            db, order, staff_user=staff, content=_PDF, filename="passport.pdf"
        )
        db.flush()

        documents = db.query(DealDocument).filter(DealDocument.deal_id == deal.id).all()
        assert [d.kind for d in documents] == [DealDocumentKind.lab_passport]
        assert order.status == LabOrderStatus.done
        assert order.result_deal_document_id == documents[0].id
        assert order.result_offer_file_id is None
        # Attributed to the party that ordered the analysis — the document is
        # theirs; who carried it is in the audit row.
        assert documents[0].uploaded_by_company_id == buyer.id

    def test_a_deal_order_does_not_touch_lab_verified_anywhere(
        self, db: Session, stub_s3: None
    ) -> None:
        """There is no offer in play: the badge belongs to a listing, and a deal
        is not one."""
        from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        order, _deal, _buyer, staff = self._deal_order(db)
        lab_service.complete_with_result(
            db, order, staff_user=staff, content=_PDF, filename="passport.pdf"
        )
        db.flush()
        assert db.query(SellerOffer).filter(SellerOffer.lab_verified.is_(True)).count() == 0

    def test_a_company_cannot_order_an_analysis_of_a_deal_it_is_not_in(
        self, db: Session
    ) -> None:
        from app.models.deals import Deal  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        buyer_owner = make_account(db, "+998900000213")
        seller_owner = make_account(db, "+998900000214")
        buyer = make_company(db, buyer_owner, tax_id="300000213")
        seller = make_company(db, seller_owner, tax_id="300000214")
        deal = Deal(
            number="DEAL-2026-000901",
            buyer_company_id=buyer.id,
            seller_company_id=seller.id,
            created_by_user_account_id=buyer_owner.id,
        )
        db.add(deal)
        db.flush()

        outsider_owner = make_account(db, "+998900000215")
        outsider = make_company(db, outsider_owner, tax_id="300000215")
        with pytest.raises(lab_service.LabOrderNotAllowed):
            lab_service.create_order(
                db, company=outsider, account=outsider_owner, deal=deal
            )


class TestResultProtection:
    def test_the_platform_result_cannot_be_removed(
        self, db: Session, stub_s3: None
    ) -> None:
        """It is the evidence behind "Laboratory Verified"; deleting it would
        leave the badge standing on nothing."""
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, staff = _scene(db)
        order = lab_service.create_order(db, company=company, account=owner, offer=offer)
        from app.models.enums import LabOrderStatus  # noqa: PLC0415

        for target in (
            LabOrderStatus.accepted,
            LabOrderStatus.sample_awaited,
            LabOrderStatus.in_analysis,
        ):
            lab_service.transition(db, order, target, staff_user=staff)
        lab_service.complete_with_result(
            db, order, staff_user=staff, content=_PDF, filename="passport.pdf"
        )
        db.flush()

        with pytest.raises(lab_service.LabResultLocked):
            lab_service.assert_result_unlocked(db, order.result_offer_file_id)

    def test_a_self_uploaded_passport_is_removable(self, db: Session) -> None:
        from app.domains.marketplace.models import SellerOfferFile  # noqa: PLC0415
        from app.models.enums import OfferFileKind  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        _company, _owner, offer, _staff = _scene(db)
        own = SellerOfferFile(
            offer_id=offer.id, kind=OfferFileKind.lab_passport, file_name="mine.pdf"
        )
        db.add(own)
        db.flush()
        lab_service.assert_result_unlocked(db, own.id)  # must not raise

    def test_removing_the_last_passport_drops_the_verification(
        self, db: Session
    ) -> None:
        from app.domains.marketplace.models import SellerOfferFile  # noqa: PLC0415
        from app.models.enums import OfferFileKind  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        _company, _owner, offer, _staff = _scene(db)
        own = SellerOfferFile(
            offer_id=offer.id, kind=OfferFileKind.lab_passport, file_name="mine.pdf"
        )
        db.add(own)
        offer.lab_verified = True
        db.flush()

        assert lab_service.clear_lab_verification(db, offer) is False  # still attached

        db.delete(own)
        db.flush()
        db.refresh(offer)
        assert lab_service.clear_lab_verification(db, offer) is True
        assert offer.lab_verified is False


class TestPartnerDirectory:
    def test_a_partner_is_retired_not_deleted(self, db: Session) -> None:
        from app.services import lab_service  # noqa: PLC0415

        staff = make_staff(db, email="admin-lab@example.com")
        partner = lab_service.create_partner(
            db,
            name="ЦентрЛаб",
            contacts={"phone": "+998712000000"},
            staff_user_id=staff.id,
        )
        lab_service.set_partner_active(db, partner, False, staff_user_id=staff.id)
        assert partner.is_active is False
        assert lab_service.get_partner(db, partner.id) is not None
        assert lab_service.list_partners(db, active_only=True) == []

    def test_assigning_a_partner_is_not_a_status_change(self, db: Session) -> None:
        from app.models.enums import LabOrderStatus  # noqa: PLC0415
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, staff = _scene(db)
        order = lab_service.create_order(db, company=company, account=owner, offer=offer)
        partner = lab_service.create_partner(db, name="ЦентрЛаб", staff_user_id=staff.id)
        lab_service.assign_partner(db, order, partner, staff_user=staff)
        assert order.lab_partner_id == partner.id
        assert order.status == LabOrderStatus.submitted


class TestQueue:
    def test_the_queue_is_oldest_first(self, db: Session) -> None:
        """Everything else in the dashboard is newest-first; a work list is the
        exception — the order waiting longest is the one to pick up."""
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, _staff = _scene(db)
        first = lab_service.create_order(db, company=company, account=owner, offer=offer)
        second = lab_service.create_order(db, company=company, account=owner, offer=offer)
        db.flush()
        assert [o.id for o in lab_service.list_queue(db)] == [first.id, second.id]

    def test_a_company_sees_only_its_own_orders(self, db: Session) -> None:
        from app.services import lab_service  # noqa: PLC0415

        company, owner, offer, _staff = _scene(db)
        mine = lab_service.create_order(db, company=company, account=owner, offer=offer)

        other_owner = make_account(db, "+998900000203")
        other = make_company(db, other_owner, tax_id="300000203")
        other_offer = make_seller_offer(db, company=other, product_text="LDPE")
        lab_service.create_order(
            db, company=other, account=other_owner, offer=other_offer
        )
        db.flush()

        assert [o.id for o in lab_service.list_for_company(db, company.id)] == [mine.id]
