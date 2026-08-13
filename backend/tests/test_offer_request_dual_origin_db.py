"""Real-Postgres tests for offer_request_service dual-origin (R2 W2 T2.2).

Guarded (localhost test_polymer only). Covers:
  * create_company_inquiry → pending company-origin inquiry (company_id +
    created_by_user_account_id set, client_id NULL); self-inquiry + non-approved
    offer guards.
  * approve of an inquiry on a COMPANY-origin offer → in-portal notification for
    the selling company's active members (kind inquiry_approved).
  * approve of an inquiry on a TG-seller offer → NO portal notification (the TG
    DM forward path is unchanged).
  * reject never forwards.
"""

from __future__ import annotations

import decimal

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_member,
    make_seller,
    make_seller_offer,
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


def _payload():  # noqa: ANN202
    from app.domains.marketplace.schemas import OfferRequestCreate  # noqa: PLC0415

    return OfferRequestCreate(
        quantity=decimal.Decimal("20.000"),
        qty_unit="MT",
        target_price=decimal.Decimal("1200.00"),
        currency="USD",
        message="Interested — please advise.",
    )


@requires_real_db
def test_create_company_inquiry_is_portal_origin(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
    from app.domains.marketplace.models import OfferRequest  # noqa: PLC0415
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415

    with sf() as db:
        seller_owner = make_account(db, "+998900002001")
        selling_co = make_company(db, seller_owner, tax_id="312000001")
        offer = make_seller_offer(db, company=selling_co)

        buyer_owner = make_account(db, "+998900002002")
        buyer_co = make_company(db, buyer_owner, tax_id="312000002")

        req = offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer, _payload()
        )
        db.commit()
        rid = req.id

    with sf() as db:
        req = db.get(OfferRequest, rid)
        assert req is not None
        assert req.client_id is None
        assert req.company_id == buyer_co.id
        assert req.created_by_user_account_id == buyer_owner.id
        assert req.status == OfferRequestStatus.pending
        assert req.origin == "company"


@requires_real_db
def test_create_company_inquiry_rejects_own_offer(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415

    with sf() as db:
        owner = make_account(db, "+998900002010")
        company = make_company(db, owner, tax_id="312000010")
        offer = make_seller_offer(db, company=company)
        db.commit()
        with pytest.raises(ValueError, match="own offer"):
            offer_request_service.create_company_inquiry(
                db, company, owner, offer, _payload()
            )


@requires_real_db
def test_create_company_inquiry_rejects_unapproved_offer(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    with sf() as db:
        seller_owner = make_account(db, "+998900002020")
        selling_co = make_company(db, seller_owner, tax_id="312000020")
        offer = make_seller_offer(db, company=selling_co, status=SellerOfferStatus.draft)
        buyer_owner = make_account(db, "+998900002021")
        buyer_co = make_company(db, buyer_owner, tax_id="312000021")
        db.commit()
        with pytest.raises(ValueError, match="not found"):
            offer_request_service.create_company_inquiry(
                db, buyer_co, buyer_owner, offer, _payload()
            )


@requires_real_db
def test_approve_company_offer_inquiry_notifies_selling_members(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
    from app.models.enums import CompanyMemberStatus  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415

    with sf() as db:
        seller_owner = make_account(db, "+998900002100")
        selling_co = make_company(db, seller_owner, tax_id="312000100")
        active = make_account(db, "+998900002101")
        removed = make_account(db, "+998900002102")
        make_member(db, selling_co, active)
        make_member(db, selling_co, removed, status=CompanyMemberStatus.removed)
        offer = make_seller_offer(db, company=selling_co)

        buyer_owner = make_account(db, "+998900002103")
        buyer_co = make_company(db, buyer_owner, tax_id="312000103")
        req = offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer, _payload()
        )
        db.commit()

        offer_request_service.moderate_offer_request(
            db, req, staff_user_id=None, approve=True
        )
        db.commit()

        notes = db.query(PortalNotification).all()
        recipients = {n.user_account_id for n in notes}
        # selling company's active members (owner + active) — NOT the removed member,
        # NOT the buyer.
        assert recipients == {seller_owner.id, active.id}
        assert all(n.kind == "inquiry_approved" for n in notes)
        assert all(n.entity == "inquiry" and n.entity_id == str(req.id) for n in notes)


@requires_real_db
def test_approve_tg_seller_offer_inquiry_makes_no_portal_notification(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415

    with sf() as db:
        seller = make_seller(db, telegram_user_id=999001)
        offer = make_seller_offer(db, seller=seller)
        buyer_owner = make_account(db, "+998900002200")
        buyer_co = make_company(db, buyer_owner, tax_id="312000200")
        req = offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer, _payload()
        )
        db.commit()

        offer_request_service.moderate_offer_request(
            db, req, staff_user_id=None, approve=True
        )
        db.commit()
        # TG-seller offer → the DM path (post-commit enqueue); moderation itself
        # creates no portal notification.
        assert db.query(sa.func.count(PortalNotification.id)).scalar() == 0


@requires_real_db
def test_reject_company_offer_inquiry_does_not_forward(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415

    with sf() as db:
        seller_owner = make_account(db, "+998900002300")
        selling_co = make_company(db, seller_owner, tax_id="312000300")
        offer = make_seller_offer(db, company=selling_co)
        buyer_owner = make_account(db, "+998900002301")
        buyer_co = make_company(db, buyer_owner, tax_id="312000301")
        req = offer_request_service.create_company_inquiry(
            db, buyer_co, buyer_owner, offer, _payload()
        )
        db.commit()

        offer_request_service.moderate_offer_request(
            db, req, staff_user_id=None, approve=False, note="No."
        )
        db.commit()
        assert db.query(sa.func.count(PortalNotification.id)).scalar() == 0
