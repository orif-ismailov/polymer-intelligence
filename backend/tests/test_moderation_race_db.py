"""
Concurrent moderation decisions are exactly-once (QA 2026-07-28 #1). Guarded real-DB.

The bug this pins: approve and reject are separate endpoints over the same queue
item, and both used to read-then-write. Fired together on one pending offer, both
answered `200` and the row ended up self-contradictory — `status=approved` carrying
the *rejection*'s `moderation_note`. Because the item was no longer pending it
dropped out of the queue, so nobody could see the corruption without reading the
raw row: an offer meant to be rejected went public.

Two sessions on a real Postgres is the only place this shows up. What is pinned:

  * **The loser loses cleanly.** The second decision updates 0 rows, raises
    `AlreadyModerated`, and leaves the winner's row untouched — no half-verdict,
    no mixed status/note.
  * **The winner's whole decision lands**, status and note together.
  * **The API says 409, not 200**, and names the status that won.
  * The same guard covers the buyer-inquiry queue, which has the identical shape.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
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


def _verified_company(db: Session):  # noqa: ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, "+998900000301")
    company = make_company(db, account, tax_id="303030303")
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _pending_offer(db: Session):  # noqa: ANN202
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    _, company = _verified_company(db)
    offer = make_seller_offer(
        db, company=company, status=SellerOfferStatus.pending_moderation
    )
    db.commit()
    return offer


# ── The race, at the service layer ────────────────────────────────────────────


def test_concurrent_approve_and_reject_leaves_one_coherent_row(engine: sa.Engine, db: Session) -> None:
    """Two moderators, two sessions, one pending offer: exactly one decision lands."""
    from app.domains.marketplace import service as offer_service  # noqa: PLC0415
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    staff = make_staff(db, email="race@example.com")
    staff_id = staff.id
    offer_id = _pending_offer(db).id

    session_a = session_factory(engine)()
    session_b = session_factory(engine)()
    try:
        offer_a = session_a.get(SellerOffer, offer_id)
        offer_b = session_b.get(SellerOffer, offer_id)
        assert offer_a is not None and offer_b is not None

        # A approves and commits. B read `pending_moderation` before that and now
        # tries to reject the same row — the old code let it through.
        offer_service.moderate_offer(session_a, offer_a, staff_id, approve=True, note="ok")
        session_a.commit()

        with pytest.raises(offer_service.AlreadyModerated) as caught:
            offer_service.moderate_offer(
                session_b, offer_b, staff_id, approve=False, note="race test reject"
            )
        session_b.rollback()
    finally:
        session_a.close()
        session_b.close()

    assert caught.value.current_status == SellerOfferStatus.approved.value

    db.expire_all()
    row = db.get(SellerOffer, offer_id)
    assert row is not None
    # The corruption the QA pass reproduced: approved + the rejection's note.
    assert row.status == SellerOfferStatus.approved
    assert row.moderation_note == "ok"
    assert row.published_at is not None


def test_a_second_decision_on_a_settled_offer_is_refused(engine: sa.Engine, db: Session) -> None:
    """Not just concurrency — a retry minutes later must not re-decide either."""
    from app.domains.marketplace import service as offer_service  # noqa: PLC0415
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    staff = make_staff(db, email="retry@example.com")
    offer = _pending_offer(db)

    offer_service.moderate_offer(db, offer, staff.id, approve=False, note="spam")
    db.commit()

    with pytest.raises(offer_service.AlreadyModerated):
        offer_service.moderate_offer(db, offer, staff.id, approve=True, note="oops")
    db.rollback()

    db.expire_all()
    row = db.get(SellerOffer, offer.id)
    assert row is not None
    assert row.status == SellerOfferStatus.rejected
    assert row.moderation_note == "spam"
    assert row.published_at is None


# ── The race, through the API ─────────────────────────────────────────────────


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN001, ANN201
    from unittest.mock import patch  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    session = session_factory(engine)()
    application = create_app()
    application.dependency_overrides[get_db] = lambda: session
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application) as client:
        yield client, session
    session.close()


def _as_analyst(application_client: TestClient, staff_id: int) -> None:
    from app.api.deps import require_analyst_or_admin  # noqa: PLC0415

    stub = type("S", (), {"id": staff_id})()
    application_client.app.dependency_overrides[require_analyst_or_admin] = lambda: stub  # type: ignore[attr-defined]


def test_api_returns_409_when_the_offer_already_left_the_queue(
    engine: sa.Engine, db: Session, api: tuple[TestClient, Session]
) -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    client, _ = api
    staff = make_staff(db, email="api@example.com")
    offer_id = _pending_offer(db).id
    _as_analyst(client, staff.id)

    first = client.post(f"/api/v1/admin/moderation/offers/{offer_id}/reject", json={"note": "no"})
    assert first.status_code == 200, first.text

    second = client.post(f"/api/v1/admin/moderation/offers/{offer_id}/approve", json={"note": "yes"})
    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail == {"code": "already_moderated", "status": SellerOfferStatus.rejected.value}


# ── Same guard on the buyer-inquiry queue ─────────────────────────────────────


def test_offer_request_second_decision_is_refused(db: Session) -> None:
    """The inquiry queue shares the offer queue's shape — and now its guard."""
    from app.domains.marketplace import requests as offer_request_service  # noqa: PLC0415
    from app.domains.marketplace.models import OfferRequest  # noqa: PLC0415
    from app.models.enums import OfferRequestStatus, SellerOfferStatus  # noqa: PLC0415

    staff = make_staff(db, email="inq@example.com")
    account, company = _verified_company(db)
    offer = make_seller_offer(db, company=company, status=SellerOfferStatus.approved)
    req = OfferRequest(
        offer_id=offer.id,
        company_id=company.id,
        created_by_user_account_id=account.id,
        quantity=10,
        status=OfferRequestStatus.pending,
    )
    db.add(req)
    db.commit()

    offer_request_service.moderate_offer_request(db, req, staff.id, approve=False, note="dup")
    db.commit()

    with pytest.raises(offer_request_service.AlreadyModerated):
        offer_request_service.moderate_offer_request(db, req, staff.id, approve=True, note="oops")
    db.rollback()

    db.expire_all()
    row = db.get(OfferRequest, req.id)
    assert row is not None
    assert row.status == OfferRequestStatus.rejected
    assert row.moderation_note == "dup"
    assert row.forwarded_at is None
