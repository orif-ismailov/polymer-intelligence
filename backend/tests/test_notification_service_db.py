"""Real-Postgres tests for notification_service (R2 W2 T2.3).

Guarded (localhost test_polymer only). Covers the stateful behaviours the mocked
API tests can't reach: insert + i18n-key persistence, kind-level dedup (skip an
identical *unread* kind+entity), per-company fan-out to active members only,
mark-read (ids / all) with cross-account isolation, unread count, and keyset
pagination of the feed.
"""

from __future__ import annotations

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
def test_notify_account_inserts_unread_row_with_i18n_keys(sf) -> None:  # noqa: ANN001
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000001")
        notif = notification_service.notify_account(
            db,
            account.id,
            kind="request_status",
            title_key="notif.request_status.title",
            body_key="notif.request_status.body",
            params={"number": "REQ-1", "status": "in_review"},
            entity="request",
            entity_id="125",
        )
        db.commit()
        assert notif is not None
        nid = notif.id

    with sf() as db:
        row = db.get(PortalNotification, nid)
        assert row is not None
        assert row.kind == "request_status"
        assert row.title_key == "notif.request_status.title"
        assert row.body_key == "notif.request_status.body"
        assert row.params == {"number": "REQ-1", "status": "in_review"}
        assert row.entity == "request"
        assert row.entity_id == "125"
        assert row.read_at is None


@requires_real_db
def test_notify_account_dedupes_identical_unread(sf) -> None:  # noqa: ANN001
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000002")
        first = notification_service.notify_account(
            db, account.id, kind="inquiry_approved",
            title_key="t", body_key="b", entity="inquiry", entity_id="7",
        )
        second = notification_service.notify_account(
            db, account.id, kind="inquiry_approved",
            title_key="t", body_key="b", entity="inquiry", entity_id="7",
        )
        db.commit()
        assert first is not None
        assert second is None  # deduped: identical unread kind+entity already exists
        count = db.query(sa.func.count(PortalNotification.id)).scalar()
        assert count == 1


@requires_real_db
def test_dedup_does_not_apply_once_read(sf) -> None:  # noqa: ANN001
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000003")
        first = notification_service.notify_account(
            db, account.id, kind="inquiry_approved",
            title_key="t", body_key="b", entity="inquiry", entity_id="7",
        )
        db.commit()
        notification_service.mark_read(db, account.id, ids=[first.id])
        db.commit()
        # Same kind+entity again — the previous one is read, so a fresh row is made.
        again = notification_service.notify_account(
            db, account.id, kind="inquiry_approved",
            title_key="t", body_key="b", entity="inquiry", entity_id="7",
        )
        db.commit()
        assert again is not None
        count = db.query(sa.func.count(PortalNotification.id)).scalar()
        assert count == 2


@requires_real_db
def test_notify_company_fans_out_to_active_members_only(sf) -> None:  # noqa: ANN001
    from app.models.enums import CompanyMemberStatus  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        owner = make_account(db, "+998900000010")
        active = make_account(db, "+998900000011")
        removed = make_account(db, "+998900000012")
        company = make_company(db, owner, tax_id="309999001")
        make_member(db, company, active)
        make_member(db, company, removed, status=CompanyMemberStatus.removed)
        db.commit()

        created = notification_service.notify_company(
            db, company.id, kind="verification_decided",
            title_key="t", body_key="b", entity="company", entity_id=str(company.id),
        )
        db.commit()
        # owner + active member get one each; removed member gets none.
        assert len(created) == 2
        recipients = {
            r.user_account_id
            for r in db.query(PortalNotification).all()
        }
        assert recipients == {owner.id, active.id}


@requires_real_db
def test_mark_read_ids_is_account_scoped(sf) -> None:  # noqa: ANN001
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        a = make_account(db, "+998900000020")
        b = make_account(db, "+998900000021")
        na = notification_service.notify_account(
            db, a.id, kind="k", title_key="t", body_key="b", entity="e", entity_id="1"
        )
        nb = notification_service.notify_account(
            db, b.id, kind="k", title_key="t", body_key="b", entity="e", entity_id="1"
        )
        db.commit()
        # Account A tries to mark B's notification read — isolation blocks it.
        marked = notification_service.mark_read(db, a.id, ids=[na.id, nb.id])
        db.commit()
        assert marked == 1  # only A's own row
        assert notification_service.unread_count(db, a.id) == 0
        assert notification_service.unread_count(db, b.id) == 1


@requires_real_db
def test_mark_all_read(sf) -> None:  # noqa: ANN001
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        a = make_account(db, "+998900000030")
        for i in range(3):
            notification_service.notify_account(
                db, a.id, kind="k", title_key="t", body_key="b",
                entity="e", entity_id=str(i),
            )
        db.commit()
        assert notification_service.unread_count(db, a.id) == 3
        marked = notification_service.mark_read(db, a.id, mark_all=True)
        db.commit()
        assert marked == 3
        assert notification_service.unread_count(db, a.id) == 0


@requires_real_db
def test_list_notifications_newest_first_with_keyset_cursor(sf) -> None:  # noqa: ANN001
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        a = make_account(db, "+998900000040")
        made = []
        for i in range(5):
            n = notification_service.notify_account(
                db, a.id, kind="k", title_key="t", body_key="b",
                entity="e", entity_id=str(i),
            )
            made.append(n)
        db.commit()
        ids_desc = [n.id for n in reversed(made)]

        page1 = notification_service.list_notifications(db, a.id, limit=2)
        assert [n.id for n in page1] == ids_desc[:2]

        page2 = notification_service.list_notifications(
            db, a.id, limit=2, cursor=page1[-1].id
        )
        assert [n.id for n in page2] == ids_desc[2:4]

        # unread_only excludes read rows
        notification_service.mark_read(db, a.id, ids=[made[0].id])
        db.commit()
        unread = notification_service.list_notifications(db, a.id, unread_only=True, limit=50)
        assert made[0].id not in {n.id for n in unread}
        assert len(unread) == 4
