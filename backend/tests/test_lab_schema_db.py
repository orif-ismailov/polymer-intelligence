"""
Lab/sample schema invariants against a real Postgres (P6 W1 — T1.1).

Three rules in this schema are not service code, and this file is what proves
they actually hold in the database rather than only in a docstring:

1. a lab order is always ABOUT something (`ck_lab_order_target`);
2. a `done` order points at the passport it produced
   (`ck_lab_order_done_has_result`) — the badge and the document cannot come
   apart;
3. one LIVE sample request per (offer, buyer), and a declined one frees the slot
   (`uq_sample_request_active`, partial).

Run with a localhost test_polymer DB; skipped otherwise (see _verification_db).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller_offer,
    migrate_head,
    session_factory,
)
from tests._verification_db import requires_real_db as requires_real_db

pytestmark = requires_real_db


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


def _scene(db: Session):  # noqa: ANN202
    """A seller company with an offer, and a buyer company."""
    seller_owner = make_account(db, "+998900000101")
    buyer_owner = make_account(db, "+998900000102")
    seller = make_company(db, seller_owner, tax_id="300000101")
    buyer = make_company(db, buyer_owner, tax_id="300000102")
    offer = make_seller_offer(db, company=seller, product_text="PP H030")
    db.flush()
    return seller, buyer, seller_owner, offer


class TestLabOrderConstraints:
    def test_an_order_about_nothing_is_rejected(self, db: Session) -> None:
        from app.domains.lab_orders.models import LabOrder  # noqa: PLC0415

        seller, _buyer, owner, _offer = _scene(db)
        db.add(
            LabOrder(
                number="LAB-2026-000001",
                company_id=seller.id,
                created_by_user_account_id=owner.id,
            )
        )
        with pytest.raises(IntegrityError, match="ck_lab_order_target"):
            db.flush()

    def test_done_without_a_result_is_rejected(self, db: Session) -> None:
        """The invariant the whole feature rests on: no badge without a document."""
        from app.domains.lab_orders.models import LabOrder  # noqa: PLC0415
        from app.models.enums import LabOrderStatus  # noqa: PLC0415

        seller, _buyer, owner, offer = _scene(db)
        db.add(
            LabOrder(
                number="LAB-2026-000002",
                company_id=seller.id,
                created_by_user_account_id=owner.id,
                offer_id=offer.id,
                status=LabOrderStatus.done,
            )
        )
        with pytest.raises(IntegrityError, match="ck_lab_order_done_has_result"):
            db.flush()

    def test_done_with_the_offer_file_is_accepted(self, db: Session) -> None:
        from app.domains.lab_orders.models import LabOrder  # noqa: PLC0415
        from app.domains.marketplace.models import SellerOfferFile  # noqa: PLC0415
        from app.models.enums import LabOrderStatus, OfferFileKind  # noqa: PLC0415

        seller, _buyer, owner, offer = _scene(db)
        passport = SellerOfferFile(
            offer_id=offer.id, kind=OfferFileKind.lab_passport, file_name="passport.pdf"
        )
        db.add(passport)
        db.flush()
        db.add(
            LabOrder(
                number="LAB-2026-000003",
                company_id=seller.id,
                created_by_user_account_id=owner.id,
                offer_id=offer.id,
                status=LabOrderStatus.done,
                result_offer_file_id=passport.id,
            )
        )
        db.flush()  # must not raise

    def test_the_number_is_unique(self, db: Session) -> None:
        from app.domains.lab_orders.models import LabOrder  # noqa: PLC0415

        seller, _buyer, owner, offer = _scene(db)
        for _ in range(2):
            db.add(
                LabOrder(
                    number="LAB-2026-000004",
                    company_id=seller.id,
                    created_by_user_account_id=owner.id,
                    offer_id=offer.id,
                )
            )
        with pytest.raises(IntegrityError):
            db.flush()


class TestSampleRequestConstraints:
    def _request(self, db: Session, offer, buyer, seller, account, **kwargs):  # noqa: ANN001, ANN003, ANN202
        from app.domains.lab_orders.models import SampleRequest  # noqa: PLC0415

        row = SampleRequest(
            offer_id=offer.id,
            buyer_company_id=buyer.id,
            seller_company_id=seller.id,
            created_by_user_account_id=account.id,
            delivery_address=kwargs.pop("delivery_address", "Tashkent, Sergeli 4"),
            **kwargs,
        )
        db.add(row)
        return row

    def test_a_company_cannot_sample_from_itself(self, db: Session) -> None:
        seller, _buyer, owner, offer = _scene(db)
        self._request(db, offer, seller, seller, owner)
        with pytest.raises(IntegrityError, match="ck_sample_parties_distinct"):
            db.flush()

    def test_only_one_live_request_per_offer_and_buyer(self, db: Session) -> None:
        seller, buyer, owner, offer = _scene(db)
        self._request(db, offer, buyer, seller, owner)
        db.flush()
        self._request(db, offer, buyer, seller, owner)
        with pytest.raises(IntegrityError, match="uq_sample_request_active"):
            db.flush()

    def test_a_declined_request_frees_the_slot(self, db: Session) -> None:
        """Partial index, like uq_rfq_response_active: being turned down once must
        not lock the buyer out of ever asking again."""
        from app.models.enums import SampleRequestStatus  # noqa: PLC0415

        seller, buyer, owner, offer = _scene(db)
        first = self._request(db, offer, buyer, seller, owner)
        db.flush()
        first.status = SampleRequestStatus.declined
        db.flush()

        self._request(db, offer, buyer, seller, owner)
        db.flush()  # must not raise

    def test_a_received_request_also_frees_the_slot(self, db: Session) -> None:
        from app.models.enums import SampleRequestStatus  # noqa: PLC0415

        seller, buyer, owner, offer = _scene(db)
        first = self._request(db, offer, buyer, seller, owner)
        db.flush()
        first.status = SampleRequestStatus.received
        db.flush()

        self._request(db, offer, buyer, seller, owner)
        db.flush()  # must not raise


class TestSellerOfferDefaults:
    def test_an_existing_offer_has_no_samples_and_no_lab_verification(
        self, db: Session
    ) -> None:
        _seller, _buyer, _owner, offer = _scene(db)
        db.commit()
        db.refresh(offer)
        assert offer.samples_available is False
        assert offer.lab_verified is False
        assert offer.sample_price is None
        assert offer.sample_dispatch_days is None

    def test_has_lab_passport_follows_the_files(self, db: Session) -> None:
        from app.domains.marketplace.models import SellerOfferFile  # noqa: PLC0415
        from app.models.enums import OfferFileKind  # noqa: PLC0415

        _seller, _buyer, _owner, offer = _scene(db)
        assert offer.has_lab_passport is False

        db.add(
            SellerOfferFile(
                offer_id=offer.id, kind=OfferFileKind.lab_passport, file_name="p.pdf"
            )
        )
        db.commit()
        db.refresh(offer)
        assert offer.has_lab_passport is True
        assert offer.lab_passport_file_id is not None
        # Uploading a passport by hand is NOT the platform's independent
        # confirmation — only a finished lab order sets that.
        assert offer.lab_verified is False
