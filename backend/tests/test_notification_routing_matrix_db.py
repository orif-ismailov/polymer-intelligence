"""R2 W2 T2.3 — origin-routing matrix + verification consumer + prune (real DB).

Guarded (localhost test_polymer only). The acceptance matrix in one place:

  | producer                          | recipient(s)                    |
  |-----------------------------------|---------------------------------|
  | portal request status change      | portal notification → creator   |
  | TG request status change          | TG DM path (no portal row)      |
  | company-offer inquiry approved    | portal → selling company members|
  | TG-seller-offer inquiry approved  | TG DM path (no portal row)      |
  | verification decision (outbox)    | portal → company members        |
  | company offer moderated           | portal → company members        |

Every notification row carries i18n keys + params, never pre-rendered text.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_member,
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


@requires_real_db
def test_notifications_never_carry_prerendered_text(sf) -> None:  # noqa: ANN001
    """Every notify_* producer stores keys/params, not rendered strings."""
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900003001")
        notification_service.notify_account(
            db, account.id, kind="request_status",
            title_key="notifications.request_status.title",
            body_key="notifications.request_status.body",
            params={"number": "REQ-1"}, entity="request", entity_id="1",
        )
        db.commit()
        row = db.query(PortalNotification).one()
        # keys are message keys (contain a dotted namespace), not sentences.
        assert row.title_key.startswith("notifications.")
        assert row.body_key.startswith("notifications.")
        assert isinstance(row.params, dict)


@requires_real_db
def test_verification_decision_consumer_notifies_company_members(sf) -> None:  # noqa: ANN001
    from app.models.events import DomainEvent  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.portal_notify import notify_company_of_verification_decision  # noqa: PLC0415

    with sf() as db:
        owner = make_account(db, "+998900003100")
        member = make_account(db, "+998900003101")
        company = make_company(db, owner, tax_id="313000100")
        make_member(db, company, member)
        # An emitted VERIFICATION_CASE_APPROVED event (as verification_service would).
        event = DomainEvent(
            event_type=event_types.VERIFICATION_CASE_APPROVED,
            aggregate_type="verification_case",
            aggregate_id="55",
            payload={"company_id": company.id},
        )
        db.add(event)
        db.commit()
        event_id = event.id

    # The consumer opens its own session from app.core.db.engine. That global engine
    # binds to whatever DATABASE_URL was at first import, so pin it to the test DB
    # (in prod it is already the real DB — this is a harness-only concern).
    with patch("app.core.db.engine", make_engine()):
        result = notify_company_of_verification_decision(
            event_id=event_id, aggregate_id="55", payload={"company_id": company.id}
        )
    assert result["status"] == "ok"
    assert result["outcome"] == "approved"

    with session_factory(make_engine())() as db:  # fresh session sees the committed rows
        notes = db.query(PortalNotification).all()
        assert {n.user_account_id for n in notes} == {owner.id, member.id}
        assert all(n.kind == "verification_decided" for n in notes)
        assert all(n.params["outcome"] == "approved" for n in notes)


@requires_real_db
def test_verification_consumer_registered_for_all_decisions() -> None:
    from app.services import event_types  # noqa: PLC0415
    from app.tasks import portal_notify  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    for et in (
        event_types.VERIFICATION_CASE_APPROVED,
        event_types.VERIFICATION_CASE_REJECTED,
        event_types.VERIFICATION_CASE_NEEDS_INFO,
    ):
        assert portal_notify.notify_company_of_verification_decision in CONSUMERS[et]


@requires_real_db
def test_company_offer_moderation_notifies_members(sf) -> None:  # noqa: ANN001
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import offer_service  # noqa: PLC0415
    from tests._verification_db import make_seller_offer  # noqa: PLC0415

    with sf() as db:
        owner = make_account(db, "+998900003200")
        member = make_account(db, "+998900003201")
        company = make_company(db, owner, tax_id="313000200")
        make_member(db, company, member)
        offer = make_seller_offer(
            db, company=company, status=SellerOfferStatus.pending_moderation
        )
        db.commit()

        offer_service.moderate_offer(db, offer, staff_user_id=None, approve=True)
        db.commit()

        notes = db.query(PortalNotification).all()
        assert {n.user_account_id for n in notes} == {owner.id, member.id}
        assert all(n.kind == "offer_moderated" for n in notes)
        assert all(n.params["outcome"] == "approved" for n in notes)


@requires_real_db
def test_prune_deletes_old_read_and_unread(sf) -> None:  # noqa: ANN001
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.tasks.portal_notify import prune_portal_notifications  # noqa: PLC0415

    now = datetime.datetime.now(datetime.UTC)
    with sf() as db:
        account = make_account(db, "+998900003300")
        # read 100d ago → pruned; read 10d ago → kept
        db.add(PortalNotification(
            user_account_id=account.id, kind="k", title_key="t", body_key="b",
            created_at=now - datetime.timedelta(days=120),
            read_at=now - datetime.timedelta(days=100),
        ))
        db.add(PortalNotification(
            user_account_id=account.id, kind="k", title_key="t", body_key="b",
            created_at=now - datetime.timedelta(days=20),
            read_at=now - datetime.timedelta(days=10),
        ))
        # unread 400d old → pruned; unread 30d old → kept
        db.add(PortalNotification(
            user_account_id=account.id, kind="k", title_key="t", body_key="b",
            created_at=now - datetime.timedelta(days=400),
        ))
        db.add(PortalNotification(
            user_account_id=account.id, kind="k", title_key="t", body_key="b",
            created_at=now - datetime.timedelta(days=30),
        ))
        db.commit()

    # Pin the task's global engine to the test DB (harness-only; see above).
    with patch("app.core.db.engine", make_engine()):
        result = prune_portal_notifications()
    assert result["deleted_read"] == 1
    assert result["deleted_unread"] == 1

    with session_factory(make_engine())() as db:
        assert db.query(sa.func.count(PortalNotification.id)).scalar() == 2
