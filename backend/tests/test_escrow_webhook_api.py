"""Escrow provider webhook (R6 / P7.b — T2.1–T2.3).

The one internet-facing unauthenticated-by-JWT surface in the product, so the
tests are about what it refuses and what it promises:

  * **no secret configured → 404.** Not 401: an endpoint that answers "wrong
    credentials" has confirmed it exists to a scanner. Every deployment that
    does not use escrow leaves `ESCROW_WEBHOOK_SECRET` empty, and for those the
    route may as well not be there.
  * **record, then answer 200, then parse.** A bank that gets a 500 retries; a
    bank that gets a 200 does not. So the response promises exactly one thing —
    "this callback is now durable" — and everything that could fail on a payload
    we do not understand happens afterwards, in the task. A callback we cannot
    read is still evidence.
  * **a repeat is one row.** Idempotency is `UNIQUE (provider, external_id)` in
    the schema, and the key is derived before parsing, so it works even for a
    body we cannot read.

Route registration is DB-free; behaviour runs against test_polymer (guarded).
"""

from __future__ import annotations

import decimal
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests._fake_redis import FakeRedis
from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_request,
    migrate_head,
    requires_real_db,
    session_factory,
)

_SECRET = "escrow-webhook-secret-for-tests"
_URL = "/api/v1/webhooks/escrow/generic"


# ── registration ──────────────────────────────────────────────────────────────


def test_route_registered() -> None:
    from app.api.webhooks_escrow import router  # noqa: PLC0415

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/webhooks/escrow/{provider}" in paths


def test_route_is_post_only() -> None:
    """No GET: a callback inbox that answers GETs invites probing."""
    from app.api.webhooks_escrow import router  # noqa: PLC0415

    methods = {m for r in router.routes for m in r.methods}  # type: ignore[attr-defined]
    assert methods == {"POST"}


def test_route_is_absent_from_the_openapi_schema() -> None:
    """An external contour is not part of our published API surface."""
    from app.api.webhooks_escrow import router  # noqa: PLC0415

    assert all(
        getattr(route, "include_in_schema", True) is False
        for route in router.routes
    )


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def api(engine: sa.Engine):  # noqa: ANN201
    """TestClient over test_polymer with the webhook secret configured."""
    from app.core.db import get_db  # noqa: PLC0415
    from app.core.redis import get_redis  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    clean(engine)
    session = session_factory(engine)
    fake_redis = FakeRedis()
    app = create_app()

    def _override_db():  # noqa: ANN202
        db = session()
        try:
            yield db
        finally:
            db.close()

    def _override_redis():  # noqa: ANN202
        yield fake_redis

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    with (
        patch("app.api.health._check_redis", return_value="ok"),
        patch("app.api.webhooks_escrow.settings.ESCROW_WEBHOOK_SECRET", _SECRET),
        TestClient(app) as client,
    ):
        yield client, session
    clean(engine)


def _live_payment(session, *, ref="ESC-1", amount=decimal.Decimal("25000.00")):  # noqa: ANN001, ANN202
    """A deal at contract_signed with escrow opened on the live rail."""
    from app.models.deals import RfqResponse  # noqa: PLC0415
    from app.models.enums import CompanyStatus, DealActorKind, DealStatus  # noqa: PLC0415
    from app.services import company_service, deal_service, escrow_service  # noqa: PLC0415

    with session() as db:
        buyer_acc = make_account(db, "+998900000001")
        seller_acc = make_account(db, "+998900000002")
        buyer = company_service.create_company(db, buyer_acc, "UZ", "301111111")
        seller = company_service.create_company(db, seller_acc, "UZ", "302222222")
        for company in (buyer, seller):
            company.status = CompanyStatus.verified
        db.flush()

        request = make_request(db, company=buyer, account=buyer_acc)
        response = RfqResponse(
            request_id=request.id,
            company_id=seller.id,
            created_by_user_account_id=seller_acc.id,
            price=decimal.Decimal("1250.00"),
            currency="USD",
            qty=decimal.Decimal("20"),
            qty_unit="MT",
        )
        db.add(response)
        db.flush()
        deal = deal_service.open_deal_from_response(db, request, response, buyer_acc)
        deal.amount = amount
        db.flush()
        for status_ in (DealStatus.contract_pending, DealStatus.contract_signed):
            deal_service.transition(db, deal, status_, actor_kind=DealActorKind.system)
        payment = escrow_service.open_for_deal(db, deal, mode="live")
        payment.provider_ref = ref
        db.commit()
        return {"deal_id": deal.id, "payment_id": payment.id}


def _body(status="funded", *, event_id="bank-op-1", ref="ESC-1", **extra):  # noqa: ANN001, ANN202
    payload = {"event_id": event_id, "escrow_ref": ref, "status": status}
    payload.update(extra)
    return payload


# ── authentication ────────────────────────────────────────────────────────────


@requires_real_db
def test_a_missing_token_is_rejected(api) -> None:  # noqa: ANN001
    client, _ = api
    assert client.post(_URL, json=_body()).status_code == 401


@requires_real_db
def test_a_wrong_token_is_rejected(api) -> None:  # noqa: ANN001
    client, _ = api
    resp = client.post(_URL, json=_body(), headers={"X-Escrow-Token": "nope"})
    assert resp.status_code == 401


@requires_real_db
def test_an_unconfigured_secret_hides_the_endpoint(api) -> None:  # noqa: ANN001
    """404, not 401 — a deployment without escrow should not advertise the rail."""
    client, _ = api
    with patch("app.api.webhooks_escrow.settings.ESCROW_WEBHOOK_SECRET", ""):
        resp = client.post(_URL, json=_body(), headers={"X-Escrow-Token": _SECRET})
    assert resp.status_code == 404


@requires_real_db
def test_a_rejected_callback_records_nothing(api) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api
    client.post(_URL, json=_body(), headers={"X-Escrow-Token": "nope"})
    with session() as db:
        assert db.query(ProviderEvent).count() == 0


# ── recording ─────────────────────────────────────────────────────────────────


@requires_real_db
def test_an_authenticated_callback_is_recorded_and_acknowledged(api) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api
    _live_payment(session)

    with patch("app.tasks.payments.apply_escrow_provider_event.apply_async") as enqueue:
        resp = client.post(_URL, json=_body(), headers={"X-Escrow-Token": _SECRET})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    with session() as db:
        event = db.query(ProviderEvent).one()
        assert event.provider == "generic"
        assert event.external_id == "bank-op-1"
        assert event.payload["status"] == "funded"
        assert event.processed is False, "the request path records; the task decides"
    enqueue.assert_called_once()


@requires_real_db
def test_a_replayed_callback_yields_exactly_one_row(api) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api
    _live_payment(session)

    with patch("app.tasks.payments.apply_escrow_provider_event.apply_async"):
        first = client.post(_URL, json=_body(), headers={"X-Escrow-Token": _SECRET})
        second = client.post(_URL, json=_body(), headers={"X-Escrow-Token": _SECRET})

    assert (first.status_code, second.status_code) == (200, 200)
    with session() as db:
        assert db.query(ProviderEvent).count() == 1


@requires_real_db
def test_an_unreadable_body_is_still_stored_and_acknowledged(api) -> None:  # noqa: ANN001
    """A bank sending XML gets a 200 and we keep the bytes.

    Refusing it would make the bank retry forever against a parser that will
    never accept it, and we would have no record of what it actually sent.
    """
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api

    with patch("app.tasks.payments.apply_escrow_provider_event.apply_async"):
        resp = client.post(
            _URL,
            content=b"<callback>funded</callback>",
            headers={"X-Escrow-Token": _SECRET, "Content-Type": "application/xml"},
        )

    assert resp.status_code == 200
    with session() as db:
        event = db.query(ProviderEvent).one()
        assert event.payload["_raw"] == "<callback>funded</callback>"
        assert event.external_id.startswith("sha256:"), "the body hash stands in as the key"


@requires_real_db
def test_a_replayed_unreadable_body_still_collapses_to_one_row(api) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api
    raw = b"<callback>funded</callback>"

    with patch("app.tasks.payments.apply_escrow_provider_event.apply_async"):
        for _ in range(2):
            client.post(
                _URL,
                content=raw,
                headers={"X-Escrow-Token": _SECRET, "Content-Type": "application/xml"},
            )

    with session() as db:
        assert db.query(ProviderEvent).count() == 1


@requires_real_db
def test_a_json_array_body_is_wrapped_rather_than_refused(api) -> None:  # noqa: ANN001
    """`payload` is JSONB of an object; a top-level array is kept verbatim as raw."""
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api

    with patch("app.tasks.payments.apply_escrow_provider_event.apply_async"):
        resp = client.post(_URL, json=[1, 2, 3], headers={"X-Escrow-Token": _SECRET})

    assert resp.status_code == 200
    with session() as db:
        assert "_raw" in db.query(ProviderEvent).one().payload


@requires_real_db
def test_an_oversized_body_is_refused(api) -> None:  # noqa: ANN001
    """A callback inbox is not a file upload endpoint."""
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api
    resp = client.post(
        _URL,
        content=b"x" * (70 * 1024),
        headers={"X-Escrow-Token": _SECRET, "Content-Type": "application/json"},
    )

    assert resp.status_code == 413
    with session() as db:
        assert db.query(ProviderEvent).count() == 0


@requires_real_db
def test_a_broker_outage_does_not_lose_the_callback(api) -> None:  # noqa: ANN001
    """The row is committed before the task is enqueued, and the sweeper is the
    reason that split exists: a Redis blip must cost latency, not evidence."""
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api
    _live_payment(session)

    with patch(
        "app.tasks.payments.apply_escrow_provider_event.apply_async",
        side_effect=RuntimeError("redis is down"),
    ):
        resp = client.post(_URL, json=_body(), headers={"X-Escrow-Token": _SECRET})

    assert resp.status_code == 200
    with session() as db:
        event = db.query(ProviderEvent).one()
        assert event.processed is False, "the sweeper will pick it up"


@requires_real_db
def test_an_unmapped_provider_is_recorded_not_refused(api) -> None:  # noqa: ANN001
    """Evidence first. `apply_provider_event` holds it with `unknown_provider`."""
    from app.models.payments import ProviderEvent  # noqa: PLC0415

    client, session = api

    with patch("app.tasks.payments.apply_escrow_provider_event.apply_async"):
        resp = client.post(
            "/api/v1/webhooks/escrow/kapitalbank",
            json=_body(),
            headers={"X-Escrow-Token": _SECRET},
        )

    assert resp.status_code == 200
    with session() as db:
        assert db.query(ProviderEvent).one().provider == "kapitalbank"


@requires_real_db
def test_a_junk_provider_name_is_refused(api) -> None:  # noqa: ANN001
    """The provider is a column value, not free text from the network."""
    client, _ = api
    resp = client.post(
        "/api/v1/webhooks/escrow/../../etc/passwd",
        json=_body(),
        headers={"X-Escrow-Token": _SECRET},
    )
    assert resp.status_code in {404, 422}


# ── the full loop, through the task ───────────────────────────────────────────


@requires_real_db
def test_the_callback_reaches_the_payment_through_the_task(api) -> None:  # noqa: ANN001
    """End to end with the Celery task called synchronously: bank → 200 → payment."""
    from app.models.deals import Deal  # noqa: PLC0415
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.models.payments import EscrowPayment, ProviderEvent  # noqa: PLC0415
    from app.tasks.payments import apply_escrow_provider_event  # noqa: PLC0415

    client, session = api
    scene = _live_payment(session)

    with patch("app.tasks.payments.apply_escrow_provider_event.apply_async"):
        client.post(_URL, json=_body(), headers={"X-Escrow-Token": _SECRET})

    with session() as db:
        event_id = db.query(ProviderEvent).one().id

    # The task opens its own session off `app.core.db.engine`, which conftest
    # points at a placeholder URL — bind it to test_polymer for the call.
    with patch("app.core.db.engine", make_engine()):
        result = apply_escrow_provider_event(event_id)
    assert result["status"] == "applied"

    with session() as db:
        payment = db.get(EscrowPayment, scene["payment_id"])
        deal = db.get(Deal, scene["deal_id"])
        assert payment is not None and deal is not None
        assert payment.status == EscrowStatus.funded
        assert deal.status == DealStatus.paid_escrow


@requires_real_db
def test_the_sweeper_picks_up_what_the_broker_dropped(api) -> None:  # noqa: ANN001
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.models.payments import EscrowPayment  # noqa: PLC0415
    from app.tasks.payments import sweep_provider_events  # noqa: PLC0415

    client, session = api
    scene = _live_payment(session)

    with patch(
        "app.tasks.payments.apply_escrow_provider_event.apply_async",
        side_effect=RuntimeError("redis is down"),
    ):
        client.post(_URL, json=_body(), headers={"X-Escrow-Token": _SECRET})

    with patch("app.core.db.engine", make_engine()):
        result = sweep_provider_events()
        assert result["processed"] == 1

        with session() as db:
            payment = db.get(EscrowPayment, scene["payment_id"])
            assert payment is not None
            assert payment.status == EscrowStatus.funded

        # Nothing left to sweep — the second run is inert.
        assert sweep_provider_events()["processed"] == 0


@requires_real_db
def test_the_task_never_raises_on_a_missing_event(api) -> None:  # noqa: ANN001
    """A task that throws has the sweeper retry it forever."""
    from app.tasks.payments import apply_escrow_provider_event  # noqa: PLC0415

    _client, _session = api
    with patch("app.core.db.engine", make_engine()):
        assert apply_escrow_provider_event(999999)["status"] == "skipped"
