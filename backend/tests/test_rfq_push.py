"""RFQ supplier push (P4 W3 — T3.3 + T3.4).

Wiring checks are DB-free; behaviour runs against test_polymer (guarded).

Three rules carry this feature:
  * it is OFF by default — a push is unsolicited mail, so it ships dark;
  * a supplier hears about one RFQ once, enforced by a unique index rather than
    by the task remembering;
  * the deeplink goes to the SUPPLIER's view of the RFQ, not the buyer's — the
    buyer's request page is company-scoped and a supplier cannot open it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_request,
    make_seller_offer,
    migrate_head,
    requires_real_db,
    session_factory,
)


def test_task_module_is_loaded_for_the_worker() -> None:
    from app.tasks.celery_app import _TASK_MODULES  # noqa: PLC0415

    assert "app.tasks.rfq_push" in _TASK_MODULES, (
        "autodiscover is a no-op here — an unlisted module is an "
        "'unregistered task' at dispatch time"
    )


def test_it_runs_on_the_notify_queue() -> None:
    from app.tasks.rfq_push import notify_matched_suppliers  # noqa: PLC0415

    assert notify_matched_suppliers.queue == "notify"


def test_the_settings_exist_and_ship_dark() -> None:
    """A push is unsolicited mail. It must not start flowing the moment this
    deploys — an operator turns it on deliberately."""
    from app.services.settings_service import _SPECS  # noqa: PLC0415

    assert _SPECS["rfq_supplier_push_enabled"].default is False
    assert _SPECS["rfq_supplier_push_top_n"].default == 10


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _enable(db, **overrides) -> None:  # noqa: ANN001, ANN003
    from app.services import settings_service  # noqa: PLC0415

    settings_service.set_many(
        db, {"rfq_supplier_push_enabled": True, **overrides}, None
    )
    db.commit()


def _supplier(db, tax, phone, *, roles=()):  # noqa: ANN001, ANN202
    from app.core.time import utcnow  # noqa: PLC0415
    from app.domains.companies.models import CompanyBusinessRole  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        BusinessRoleStatus,
        CompanyStatus,
        SellerOfferStatus,
    )

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax)
    company.status = CompanyStatus.verified
    company.legal_name = f"OOO {tax}"
    db.flush()
    for role in roles:
        db.add(
            CompanyBusinessRole(
                company_id=company.id, role=role, status=BusinessRoleStatus.confirmed
            )
        )
    offer = make_seller_offer(db, company=company, status=SellerOfferStatus.approved)
    offer.published_at = utcnow()
    db.flush()
    return company, account


def _scene(db):  # noqa: ANN001, ANN202
    buyer_acc = make_account(db, "+998900000001")
    buyer = make_company(db, buyer_acc, tax_id="301111111")
    request = make_request(db, company=buyer, account=buyer_acc, product_text="HDPE film")
    supplier, supplier_acc = _supplier(db, "302222222", "+998900000002")
    db.commit()
    return request, supplier, supplier_acc


def _fire(request_id: int) -> dict:
    """Run the task the way the enqueue would, against the test DB."""
    from app.tasks.rfq_push import notify_matched_suppliers  # noqa: PLC0415

    with patch("app.core.db.engine", make_engine()):
        return notify_matched_suppliers(request_id)


@requires_real_db
def test_the_gate_is_off_by_default(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace.models import RfqPushLog  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415

    with sf() as db:
        request, _supplier_co, _acc = _scene(db)
        request_id = request.id

    assert _fire(request_id)["status"] == "disabled"

    with sf() as db:
        assert db.query(RfqPushLog).count() == 0
        assert db.query(PortalNotification).count() == 0


@requires_real_db
def test_a_matched_supplier_is_logged_and_notified(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace.models import RfqPushLog  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from app.services import notification_service  # noqa: PLC0415

    with sf() as db:
        request, supplier, supplier_acc = _scene(db)
        _enable(db)
        request_id, supplier_id, acc_id = request.id, supplier.id, supplier_acc.id
        number = request.number

    result = _fire(request_id)
    assert result["status"] == "ok"
    assert result["notified"] == 1

    with sf() as db:
        logged = db.query(RfqPushLog).one()
        assert logged.request_id == request_id
        assert logged.company_id == supplier_id
        assert logged.rank == 1
        assert logged.score > 0

        bell = db.query(PortalNotification).one()
        assert bell.user_account_id == acc_id
        assert bell.kind == notification_service.KIND_RFQ_MATCH
        # The SUPPLIER's view of the RFQ, not the buyer's company-scoped page.
        assert bell.entity == "rfq"
        assert bell.entity_id == str(request_id)
        assert bell.params["number"] == number
        assert bell.params["product"]


@requires_real_db
def test_running_it_twice_notifies_nobody_twice(sf) -> None:  # noqa: ANN001
    """FR-A2. The unique index is the guard, not the task's memory — so a retry
    after a crash mid-run is safe too."""
    from app.domains.marketplace.models import RfqPushLog  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415

    with sf() as db:
        request, _supplier_co, _acc = _scene(db)
        _enable(db)
        request_id = request.id

    first = _fire(request_id)
    second = _fire(request_id)

    assert first["notified"] == 1
    assert second["notified"] == 0
    with sf() as db:
        assert db.query(RfqPushLog).count() == 1
        assert db.query(PortalNotification).count() == 1


@requires_real_db
def test_top_n_caps_the_blast(sf) -> None:  # noqa: ANN001
    from app.domains.marketplace.models import RfqPushLog  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        request = make_request(
            db, company=buyer, account=buyer_acc, product_text="HDPE film"
        )
        for index in range(5):
            _supplier(db, f"30222222{index}", f"+99890000200{index}")
        db.commit()
        _enable(db, rfq_supplier_push_top_n=2)
        request_id = request.id

    assert _fire(request_id)["notified"] == 2
    with sf() as db:
        ranks = sorted(r.rank for r in db.query(RfqPushLog).all())
        assert ranks == [1, 2], "the top-ranked suppliers, not an arbitrary two"


@requires_real_db
def test_every_active_member_of_a_matched_supplier_hears(sf) -> None:  # noqa: ANN001
    from app.models.enums import CompanyMemberRole  # noqa: PLC0415
    from app.models.notifications import PortalNotification  # noqa: PLC0415
    from tests._verification_db import make_member  # noqa: PLC0415

    with sf() as db:
        request, supplier, _acc = _scene(db)
        colleague = make_account(db, "+998900000009")
        make_member(db, supplier, colleague, role=CompanyMemberRole.manager)
        _enable(db)
        request_id = request.id

    _fire(request_id)
    with sf() as db:
        assert db.query(PortalNotification).count() == 2


@requires_real_db
def test_a_request_with_no_matches_is_not_an_error(sf) -> None:  # noqa: ANN001
    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        request = make_request(
            db, company=buyer, account=buyer_acc, product_text="Unobtanium"
        )
        db.commit()
        _enable(db)
        request_id = request.id

    result = _fire(request_id)
    assert result["status"] == "ok"
    assert result["notified"] == 0


@requires_real_db
def test_a_missing_request_never_raises(sf) -> None:  # noqa: ANN001
    """A task that raises gets retried by Celery forever; a vanished request is
    not a transient failure."""
    with sf() as db:
        _enable(db)
    assert _fire(999999)["status"] == "skipped"


@requires_real_db
def test_publishing_an_rfq_enqueues_the_push(sf) -> None:  # noqa: ANN001
    """The trigger point: a company filing an RFQ. Enqueue is fail-soft — a
    broker outage must not break request creation."""
    from app.schemas.webapp import RequestCreate  # noqa: PLC0415
    from app.services import request_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        db.commit()

        payload = RequestCreate(
            product_text="HDPE film",
            grade_text="F0348",
            volume="20",
            volume_unit="MT",
            destination_country="UZ",
            validity_days=14,
        )
        with patch("app.tasks.rfq_push.notify_matched_suppliers.apply_async") as enqueue:
            created = request_service.create_company_request(db, buyer, buyer_acc, payload)
            db.commit()
        assert enqueue.called, "publishing an RFQ must enqueue the supplier push"
        assert enqueue.call_args.kwargs["args"] == [created.id]


@requires_real_db
def test_a_broker_outage_does_not_break_rfq_creation(sf) -> None:  # noqa: ANN001
    from app.schemas.webapp import RequestCreate  # noqa: PLC0415
    from app.services import request_service  # noqa: PLC0415

    with sf() as db:
        buyer_acc = make_account(db, "+998900000001")
        buyer = make_company(db, buyer_acc, tax_id="301111111")
        db.commit()

        payload = RequestCreate(
            product_text="HDPE film",
            grade_text="F0348",
            volume="20",
            volume_unit="MT",
            destination_country="UZ",
            validity_days=14,
        )
        with patch(
            "app.tasks.rfq_push.notify_matched_suppliers.apply_async",
            side_effect=OSError("broker down"),
        ):
            created = request_service.create_company_request(db, buyer, buyer_acc, payload)
            db.commit()
        assert created.id is not None


@requires_real_db
def test_staff_can_see_who_was_notified(sf) -> None:  # noqa: ANN001
    """T3.4: without this the push is invisible to the team supporting it."""
    from app.services import rfq_push_service  # noqa: PLC0415

    with sf() as db:
        request, supplier, _acc = _scene(db)
        _enable(db)
        request_id, supplier_id = request.id, supplier.id

    _fire(request_id)

    with sf() as db:
        rows = rfq_push_service.list_pushed(db, request_id)
        assert len(rows) == 1
        assert rows[0].company_id == supplier_id
        assert rows[0].company_name == "OOO 302222222"
        assert rows[0].rank == 1
