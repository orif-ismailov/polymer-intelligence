"""Real-Postgres tests for request_service dual-origin (R2 W2 T2.1).

Guarded (localhost test_polymer only). Covers:
  * create_company_request → portal-origin request (company_id +
    created_by_user_account_id set, client_id NULL, status new, initial history),
    and no self-notification on creation.
  * transition_status on a portal-origin request → an in-portal notification for
    the creator (kind=request_status), and NO TG DM path.
  * transition_status on a TG-origin request → NO portal notification (TG DM path
    unchanged).
"""

from __future__ import annotations

import decimal
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
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
    from app.models.enums import PriceBasis, Urgency  # noqa: PLC0415
    from app.schemas.webapp import RequestCreate  # noqa: PLC0415

    return RequestCreate(
        product_id=None,
        product_text="HDPE film grade",
        grade_text="F0348",
        polymer_type="HDPE",
        volume=decimal.Decimal("50.000"),
        volume_unit="MT",
        target_price=decimal.Decimal("1100.00"),
        currency="USD",
        incoterms=PriceBasis.CIF,
        destination_country="UZ",
        urgency=Urgency.high,
        comment="Portal request",
    )


@requires_real_db
def test_create_company_request_is_portal_origin(sf) -> None:  # noqa: ANN001
    from app.models.enums import RequestStatus  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.models.requests import Request, RequestStatusHistory  # noqa: PLC0415
    from app.services import request_service  # noqa: PLC0415

    with sf() as db:
        owner = make_account(db, "+998900001001")
        company = make_company(db, owner, tax_id="311000001")
        req = request_service.create_company_request(db, company, owner, _payload())
        db.commit()
        rid = req.id

    with sf() as db:
        req = db.get(Request, rid)
        assert req is not None
        assert req.client_id is None
        assert req.company_id == company.id
        assert req.created_by_user_account_id == owner.id
        assert req.status == RequestStatus.new
        assert req.origin == "company"
        assert req.number.startswith("REQ-")
        hist = (
            db.query(RequestStatusHistory)
            .filter(RequestStatusHistory.request_id == rid)
            .all()
        )
        assert len(hist) == 1
        assert hist[0].to_status == RequestStatus.new
        # No self-notification on creation.
        assert db.query(sa.func.count(PortalNotification.id)).scalar() == 0


@requires_real_db
def test_transition_portal_request_notifies_creator_in_portal(sf) -> None:  # noqa: ANN001
    from app.models.enums import RequestStatus  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import request_service  # noqa: PLC0415

    with sf() as db:
        owner = make_account(db, "+998900001002")
        company = make_company(db, owner, tax_id="311000002")
        req = request_service.create_company_request(db, company, owner, _payload())
        db.commit()

        # Staff moves new -> viewed. No TG DM should be enqueued for a portal request.
        with patch(
            "app.services.request_service._enqueue_notify_soft"
        ) as tg_enqueue:
            request_service.transition_status(
                db, req, RequestStatus.viewed, changed_by=None
            )
            db.commit()
            tg_enqueue.assert_not_called()

        notes = db.query(PortalNotification).all()
        assert len(notes) == 1
        note = notes[0]
        assert note.user_account_id == owner.id
        assert note.kind == "request_status"
        assert note.entity == "request"
        assert note.entity_id == str(req.id)
        assert note.params["number"] == req.number
        assert note.params["status"] == "in_review"  # viewed -> in_review (CLIENT_STATUS_MAP)


@requires_real_db
def test_transition_tg_request_uses_tg_dm_not_portal(sf) -> None:  # noqa: ANN001
    from app.models.enums import RequestStatus  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.models.requests import Client, Request  # noqa: PLC0415
    from app.services import request_service  # noqa: PLC0415

    with sf() as db:
        client = Client(telegram_user_id=555001, language="ru")
        db.add(client)
        db.flush()
        req = Request(
            number="REQ-2026-07-25-00001",
            client_id=client.id,
            status=RequestStatus.new,
            product_text="LDPE",
            grade_text="X",
            volume=decimal.Decimal("10.000"),
            volume_unit="MT",
        )
        db.add(req)
        db.flush()

        with patch(
            "app.services.request_service._enqueue_notify_soft"
        ) as tg_enqueue:
            request_service.transition_status(
                db, req, RequestStatus.viewed, changed_by=None
            )
            db.commit()
            tg_enqueue.assert_called_once_with(req.id)

        # No portal notification for a TG-origin request.
        assert db.query(sa.func.count(PortalNotification.id)).scalar() == 0
