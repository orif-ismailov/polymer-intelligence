"""
Sample requests end to end against a real Postgres (P6 W3 — T3.1).

The machine is pinned by `test_sample_service.py` (a table, no database). What
needs a database is the gate around creating one, the one-live-request rule that
lives in a partial index rather than an `if`, and the bells — each of which must
reach the party that did NOT act.

Run with a localhost test_polymer DB; skipped otherwise (see _verification_db).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller,
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


def _scene(db: Session, *, samples: bool = True):  # noqa: ANN202
    """A seller with a sampleable approved offer, and a buyer company."""
    seller_owner = make_account(db, "+998900000401")
    buyer_owner = make_account(db, "+998900000402")
    seller = make_company(db, seller_owner, tax_id="300000401")
    buyer = make_company(db, buyer_owner, tax_id="300000402")
    offer = make_seller_offer(
        db, company=seller, product_text="PP H030", samples_available=samples
    )
    db.flush()
    return seller, buyer, buyer_owner, offer


class TestRequesting:
    def test_a_buyer_asks_for_a_sample(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus  # noqa: PLC0415

        seller, buyer, buyer_owner, offer = _scene(db)
        sample = sample_service.request(
            db,
            offer=offer,
            buyer_company=buyer,
            account=buyer_owner,
            delivery_address="Ташкент, Сергели 4",
            qty="1 кг",
        )
        assert sample.status == SampleRequestStatus.requested
        # Copied, not followed: the seller's inbox must not depend on the offer
        # never being edited.
        assert sample.seller_company_id == seller.id

    def test_an_offer_without_samples_is_refused(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415

        _seller, buyer, buyer_owner, offer = _scene(db, samples=False)
        with pytest.raises(sample_service.SamplesNotAvailable):
            sample_service.request(
                db,
                offer=offer,
                buyer_company=buyer,
                account=buyer_owner,
                delivery_address="Ташкент",
            )

    def test_a_telegram_sellers_offer_cannot_be_sampled(self, db: Session) -> None:
        """There is no portal account behind it to accept or enter a tracking
        number, so the request would have nowhere to go."""
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415

        _seller, buyer, buyer_owner, _offer = _scene(db)
        tg_seller = make_seller(db, telegram_user_id=555001)
        tg_offer = make_seller_offer(
            db, seller=tg_seller, product_text="LDPE", samples_available=True
        )
        with pytest.raises(sample_service.SamplesNotAvailable):
            sample_service.request(
                db,
                offer=tg_offer,
                buyer_company=buyer,
                account=buyer_owner,
                delivery_address="Ташкент",
            )

    def test_a_company_cannot_sample_its_own_offer(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415

        seller, _buyer, _buyer_owner, offer = _scene(db)
        seller_owner = make_account(db, "+998900000403")
        with pytest.raises(sample_service.OwnOfferSample):
            sample_service.request(
                db,
                offer=offer,
                buyer_company=seller,
                account=seller_owner,
                delivery_address="Ташкент",
            )

    def test_a_second_live_request_is_a_typed_error_not_a_crash(
        self, db: Session
    ) -> None:
        """The partial unique index IS the rule; the savepoint keeps a lost race
        from poisoning the caller's transaction."""
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415

        _seller, buyer, buyer_owner, offer = _scene(db)
        sample_service.request(
            db,
            offer=offer,
            buyer_company=buyer,
            account=buyer_owner,
            delivery_address="Ташкент",
        )
        with pytest.raises(sample_service.SampleRequestExists):
            sample_service.request(
                db,
                offer=offer,
                buyer_company=buyer,
                account=buyer_owner,
                delivery_address="Ташкент",
            )
        # The session is still usable — that is the point of the savepoint. A
        # poisoned transaction would raise PendingRollbackError here instead.
        from app.domains.lab_orders.models import SampleRequest  # noqa: PLC0415

        assert db.query(SampleRequest).count() == 1

    def test_after_a_decline_the_buyer_may_ask_again(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus  # noqa: PLC0415

        seller, buyer, buyer_owner, offer = _scene(db)
        first = sample_service.request(
            db,
            offer=offer,
            buyer_company=buyer,
            account=buyer_owner,
            delivery_address="Ташкент",
        )
        sample_service.transition(
            db,
            first,
            SampleRequestStatus.declined,
            acting_company_id=seller.id,
            reason="нет остатка",
        )
        again = sample_service.request(
            db,
            offer=offer,
            buyer_company=buyer,
            account=buyer_owner,
            delivery_address="Ташкент",
        )
        assert again.id != first.id

    def test_the_seller_is_told(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.notifications import PortalNotification  # noqa: PLC0415
        from app.services import notification_service  # noqa: PLC0415

        seller, buyer, buyer_owner, offer = _scene(db)
        sample_service.request(
            db,
            offer=offer,
            buyer_company=buyer,
            account=buyer_owner,
            delivery_address="Ташкент",
        )
        db.flush()
        rows = (
            db.query(PortalNotification)
            .filter(
                PortalNotification.kind == notification_service.KIND_SAMPLE_REQUEST_NEW
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].entity == "sample_request"


class TestMoving:
    def _requested(self, db: Session):  # noqa: ANN202
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415

        seller, buyer, buyer_owner, offer = _scene(db)
        sample = sample_service.request(
            db,
            offer=offer,
            buyer_company=buyer,
            account=buyer_owner,
            delivery_address="Ташкент, Сергели 4",
        )
        return sample, seller, buyer

    def test_the_full_round_trip(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus as S  # noqa: PLC0415

        sample, seller, buyer = self._requested(db)

        sample_service.transition(db, sample, S.accepted, acting_company_id=seller.id)
        assert sample.accepted_at is not None

        sample_service.transition(
            db,
            sample,
            S.sent,
            acting_company_id=seller.id,
            qty="1 кг",
            courier="BTS Express",
            tracking_ref="BTS-77123",
        )
        assert sample.sent_at is not None
        assert sample.tracking_ref == "BTS-77123"

        sample_service.transition(db, sample, S.received, acting_company_id=buyer.id)
        assert sample.status == S.received
        assert sample.received_at is not None

    def test_a_seller_cannot_confirm_the_delivery(self, db: Session) -> None:
        """The move this table exists to prevent: it would close their own dispute."""
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus as S  # noqa: PLC0415

        sample, seller, _buyer = self._requested(db)
        sample_service.transition(db, sample, S.accepted, acting_company_id=seller.id)
        sample_service.transition(
            db,
            sample,
            S.sent,
            acting_company_id=seller.id,
            courier="BTS",
            tracking_ref="X1",
        )
        with pytest.raises(sample_service.ActorNotAllowed):
            sample_service.transition(db, sample, S.received, acting_company_id=seller.id)

    def test_a_buyer_cannot_invent_a_shipment(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus as S  # noqa: PLC0415

        sample, seller, buyer = self._requested(db)
        sample_service.transition(db, sample, S.accepted, acting_company_id=seller.id)
        with pytest.raises(sample_service.ActorNotAllowed):
            sample_service.transition(
                db,
                sample,
                S.sent,
                acting_company_id=buyer.id,
                courier="BTS",
                tracking_ref="X1",
            )

    def test_shipping_without_a_tracking_reference_is_refused(
        self, db: Session
    ) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus as S  # noqa: PLC0415

        sample, seller, _buyer = self._requested(db)
        sample_service.transition(db, sample, S.accepted, acting_company_id=seller.id)
        with pytest.raises(sample_service.ShipmentDetailsRequired):
            sample_service.transition(
                db, sample, S.sent, acting_company_id=seller.id, courier="BTS"
            )

    def test_declining_without_a_reason_is_refused(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus as S  # noqa: PLC0415

        sample, seller, _buyer = self._requested(db)
        with pytest.raises(sample_service.ReasonRequired):
            sample_service.transition(db, sample, S.declined, acting_company_id=seller.id)

    def test_an_outsider_cannot_touch_it(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus as S  # noqa: PLC0415

        sample, _seller, _buyer = self._requested(db)
        outsider_owner = make_account(db, "+998900000404")
        outsider = make_company(db, outsider_owner, tax_id="300000404")
        with pytest.raises(sample_service.NotSampleParty):
            sample_service.transition(db, sample, S.accepted, acting_company_id=outsider.id)

    def test_each_move_tells_the_other_side(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus as S  # noqa: PLC0415
        from app.models.notifications import PortalNotification  # noqa: PLC0415
        from app.services import notification_service  # noqa: PLC0415
        from tests._verification_db import make_member  # noqa: PLC0415

        sample, seller, buyer = self._requested(db)
        # A second person in the buyer company, to prove the fan-out reaches the
        # company rather than just the person who clicked.
        second = make_account(db, "+998900000405")
        make_member(db, buyer, second)
        db.flush()

        sample_service.transition(db, sample, S.accepted, acting_company_id=seller.id)
        db.flush()

        rows = (
            db.query(PortalNotification)
            .filter(
                PortalNotification.kind
                == notification_service.KIND_SAMPLE_REQUEST_STATUS
            )
            .all()
        )
        # Both members of the BUYER company — the side that did not act.
        assert len(rows) == 2
        assert {r.params["status"] for r in rows} == {"accepted"}

    def test_two_moves_produce_two_bells(self, db: Session) -> None:
        """dedup=False: "accepted" and "shipped" are different sentences."""
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415
        from app.models.enums import SampleRequestStatus as S  # noqa: PLC0415
        from app.models.notifications import PortalNotification  # noqa: PLC0415
        from app.services import notification_service  # noqa: PLC0415

        sample, seller, _buyer = self._requested(db)
        sample_service.transition(db, sample, S.accepted, acting_company_id=seller.id)
        sample_service.transition(
            db,
            sample,
            S.sent,
            acting_company_id=seller.id,
            courier="BTS",
            tracking_ref="X1",
        )
        db.flush()
        rows = (
            db.query(PortalNotification)
            .filter(
                PortalNotification.kind
                == notification_service.KIND_SAMPLE_REQUEST_STATUS
            )
            .all()
        )
        assert {r.params["status"] for r in rows} == {"accepted", "sent"}


class TestLists:
    def test_each_side_sees_its_own_column(self, db: Session) -> None:
        from app.domains.lab_orders import samples as sample_service  # noqa: PLC0415

        seller, buyer, buyer_owner, offer = _scene(db)
        sample = sample_service.request(
            db,
            offer=offer,
            buyer_company=buyer,
            account=buyer_owner,
            delivery_address="Ташкент",
        )
        db.flush()

        assert [s.id for s in sample_service.list_for_company(db, seller.id, side="incoming")] == [
            sample.id
        ]
        assert sample_service.list_for_company(db, seller.id, side="sent") == []
        assert [s.id for s in sample_service.list_for_company(db, buyer.id, side="sent")] == [
            sample.id
        ]
        assert sample_service.list_for_company(db, buyer.id, side="incoming") == []
