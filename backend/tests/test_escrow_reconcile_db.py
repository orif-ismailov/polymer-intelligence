"""Escrow ↔ bank reconciliation (R6 / P7.b — T3.1). Guarded (test_polymer).

Didox has no partner webhooks and the bank's notification format is unknown, so
polling is not a fallback here — it is the mechanism we can be sure of. This is
the only part of the rail that CALLS OUT, which is why it runs on the `verify`
queue.

The design decision these tests exist to protect: a polled status is turned into
a **synthesized callback row** and pushed through the same
`apply_provider_event` as a real webhook. One path from "the provider says X" to
"we did Y" — a second, parallel path would be the one where a guard is
eventually forgotten. It also makes the poll idempotent for free: the synthetic
`external_id` is deterministic per (reference, status), so re-polling an
unchanged divergence collides on the inbox's unique index instead of alerting
every five minutes.

`LiveEscrowClient` is deliberately absent — the bank's specification has not
arrived. The RULES are what this wave delivers, and a fake bank proves them.
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
    make_request,
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


class _FakeBank:
    """An escrow provider that reports whatever the test tells it to."""

    def __init__(self, statuses: dict[str, str | None], *, down: bool = False) -> None:
        self._statuses = statuses
        self._down = down
        self.asked: list[str] = []

    def open_escrow(self, *, deal_id: int, amount: str, currency: str) -> object:
        raise AssertionError("reconciliation must not open escrows")

    def get_status(self, provider_ref: str) -> str | None:
        from app.integrations.escrow.client import ProviderUnavailable  # noqa: PLC0415

        if self._down:
            raise ProviderUnavailable("bank is down")
        self.asked.append(provider_ref)
        return self._statuses.get(provider_ref)

    def request_release(self, provider_ref: str) -> bool:
        return False

    def request_refund(self, provider_ref: str) -> bool:
        return False


# ── scene ─────────────────────────────────────────────────────────────────────


def _verified(db, tax, phone):  # noqa: ANN001, ANN202
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    account = make_account(db, phone)
    company = make_company(db, account, tax_id=tax)
    company.status = CompanyStatus.verified
    db.flush()
    return account, company


def _payment(db, *, mode="live", ref="ESC-1", amount=decimal.Decimal("25000.00")):  # noqa: ANN001, ANN202
    from app.models.deals import RfqResponse  # noqa: PLC0415
    from app.models.enums import DealActorKind, DealStatus  # noqa: PLC0415
    from app.services import deal_service, escrow_service  # noqa: PLC0415

    buyer_acc, buyer = _verified(db, "301111111", "+998900000001")
    seller_acc, seller = _verified(db, "302222222", "+998900000002")
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
    payment = escrow_service.open_for_deal(db, deal, mode=mode)
    payment.provider_ref = ref
    db.flush()
    return payment, deal, buyer_acc, buyer, seller_acc, seller


def _deliver(db, deal, buyer_acc, buyer, seller_acc, seller):  # noqa: ANN001
    from app.models.enums import DealStatus  # noqa: PLC0415
    from app.services import deal_service  # noqa: PLC0415

    deal_service.transition_by_party(db, deal, seller_acc, DealStatus.shipped, company_id=seller.id)
    deal_service.transition_by_party(db, deal, buyer_acc, DealStatus.delivered, company_id=buyer.id)


# ── agreement and advance ─────────────────────────────────────────────────────


@requires_real_db
def test_agreement_changes_nothing_and_writes_no_event(sf) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        _payment(db)
        db.commit()

        report = escrow_service.reconcile_with_provider(db, _FakeBank({"ESC-1": "pending"}))
        db.commit()

        assert report["agreed"] == 1
        assert report["applied"] == 0
        assert db.query(ProviderEvent).count() == 0, (
            "agreement is not an event — the inbox is for movements"
        )


@requires_real_db
def test_a_funded_status_is_applied_through_the_same_door_as_a_webhook(sf) -> None:  # noqa: ANN001
    from app.models.enums import DealStatus, EscrowStatus  # noqa: PLC0415
    from app.models.payments import ProviderEvent  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        payment, deal, *_ = _payment(db)
        db.commit()

        report = escrow_service.reconcile_with_provider(db, _FakeBank({"ESC-1": "funded"}))
        db.commit()

        assert report["applied"] == 1
        db.refresh(payment)
        db.refresh(deal)
        assert payment.status == EscrowStatus.funded
        assert deal.status == DealStatus.paid_escrow
        # A synthesized callback row, so the audit trail of a polled movement is
        # indistinguishable in shape from a pushed one.
        event = db.query(ProviderEvent).one()
        assert event.external_id == "poll:ESC-1:funded"
        assert event.processed is True
        assert payment.funded_marked_by is None


@requires_real_db
def test_re_polling_an_unchanged_status_is_inert(sf) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        _payment(db)
        db.commit()
        bank = _FakeBank({"ESC-1": "funded"})

        escrow_service.reconcile_with_provider(db, bank)
        db.commit()
        second = escrow_service.reconcile_with_provider(db, bank)
        db.commit()

        assert second["applied"] == 0
        assert second["agreed"] == 1, "we now match the bank"
        assert db.query(ProviderEvent).count() == 1


# ── divergence: alert, never an auto-transition ───────────────────────────────


@requires_real_db
def test_a_release_before_delivery_is_reported_not_applied(sf) -> None:  # noqa: ANN001
    """The skeleton's acceptance criterion, verbatim: bank released, deal not
    delivered → an alert, not an auto-transition."""
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _payment(db)
        db.commit()
        escrow_service.reconcile_with_provider(db, _FakeBank({"ESC-1": "funded"}))
        db.commit()

        report = escrow_service.reconcile_with_provider(db, _FakeBank({"ESC-1": "released"}))
        db.commit()

        assert report["held"] == 1
        assert report["applied"] == 0
        assert escrow_service.HOLD_RELEASE_BEFORE_DELIVERY in report["reasons"]
        assert payment.id in report["held_payment_ids"]
        db.refresh(payment)
        assert payment.status == EscrowStatus.funded


@requires_real_db
def test_a_refund_status_is_reported_not_applied(sf) -> None:  # noqa: ANN001
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _payment(db)
        db.commit()

        report = escrow_service.reconcile_with_provider(db, _FakeBank({"ESC-1": "refunded"}))
        db.commit()

        assert report["held"] == 1
        assert escrow_service.HOLD_NEEDS_OPERATOR in report["reasons"]
        db.refresh(payment)
        assert payment.status == EscrowStatus.pending


@requires_real_db
def test_a_standing_divergence_is_reported_once_not_every_poll(sf) -> None:  # noqa: ANN001
    """Deterministic synthetic ids mean an unresolved disagreement does not
    alert every five minutes — it alerts once and then lives in the queue."""
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        _payment(db)
        db.commit()
        bank = _FakeBank({"ESC-1": "refunded"})

        first = escrow_service.reconcile_with_provider(db, bank)
        db.commit()
        second = escrow_service.reconcile_with_provider(db, bank)
        db.commit()

        assert first["held"] == 1
        assert second["held"] == 0
        assert second["already_processed"] == 1
        assert escrow_service.held_provider_events(db), "still visible in the operator queue"


@requires_real_db
def test_an_unmodelled_provider_status_is_counted_not_guessed(sf) -> None:  # noqa: ANN001
    from app.models.payments import ProviderEvent  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        _payment(db)
        db.commit()

        report = escrow_service.reconcile_with_provider(
            db, _FakeBank({"ESC-1": "awaiting_compliance"})
        )
        db.commit()

        assert report["unmodelled"] == 1
        assert report["applied"] == 0
        assert db.query(ProviderEvent).count() == 0


@requires_real_db
def test_a_provider_that_knows_nothing_about_the_reference_is_skipped(sf) -> None:  # noqa: ANN001
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        _payment(db)
        db.commit()

        report = escrow_service.reconcile_with_provider(db, _FakeBank({}))
        db.commit()

        assert report["unknown"] == 1


# ── what is never polled ──────────────────────────────────────────────────────


@requires_real_db
def test_stub_rail_payments_are_never_polled(sf) -> None:  # noqa: ANN001
    """An operator is reconciling those by hand; a bank must not be asked."""
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        _payment(db, mode="stub")
        db.commit()

        bank = _FakeBank({"ESC-1": "funded"})
        report = escrow_service.reconcile_with_provider(db, bank)
        db.commit()

        assert report["checked"] == 0
        assert bank.asked == []


@requires_real_db
def test_terminal_payments_are_never_polled(sf) -> None:  # noqa: ANN001
    """A released payment is a finished bank operation; there is nothing to learn."""
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        payment, deal, buyer_acc, buyer, seller_acc, seller = _payment(db)
        escrow_service.reconcile_with_provider(db, _FakeBank({"ESC-1": "funded"}))
        _deliver(db, deal, buyer_acc, buyer, seller_acc, seller)
        escrow_service.reconcile_with_provider(db, _FakeBank({"ESC-1": "released"}))
        db.commit()
        db.refresh(payment)

        bank = _FakeBank({"ESC-1": "refunded"})
        report = escrow_service.reconcile_with_provider(db, bank)
        db.commit()

        assert report["checked"] == 0
        assert bank.asked == []


@requires_real_db
def test_a_payment_with_no_provider_reference_is_never_polled(sf) -> None:  # noqa: ANN001
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _payment(db)
        payment.provider_ref = None
        db.commit()

        report = escrow_service.reconcile_with_provider(db, _FakeBank({"ESC-1": "funded"}))
        db.commit()

        assert report["checked"] == 0


# ── degradation ───────────────────────────────────────────────────────────────


@requires_real_db
def test_a_dead_provider_stops_the_sweep_without_touching_anything(sf) -> None:  # noqa: ANN001
    """Provider unavailability degrades; it never moves or blocks a deal."""
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.services import escrow_service  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _payment(db)
        db.commit()

        report = escrow_service.reconcile_with_provider(db, _FakeBank({}, down=True))
        db.commit()

        assert report["unavailable"] is True
        assert report["applied"] == 0
        db.refresh(payment)
        assert payment.status == EscrowStatus.pending


# ── the beat task ─────────────────────────────────────────────────────────────


@requires_real_db
def test_the_beat_is_a_noop_while_the_rail_is_stub(sf) -> None:  # noqa: ANN001
    """`escrow_mode` ships `stub`, so the task does nothing — and says so."""
    from app.tasks.payments import reconcile_escrow_payments  # noqa: PLC0415

    with sf() as db:
        _payment(db)
        db.commit()

    with patch("app.core.db.engine", make_engine()):
        result = reconcile_escrow_payments()

    assert result["status"] == "no_provider"


@requires_real_db
def test_the_beat_is_a_noop_on_the_live_rail_with_no_adapter(sf) -> None:  # noqa: ANN001
    """`live` has no client yet (the bank's spec has not arrived), so the task
    reports honestly instead of raising or silently using the stub."""
    from app.services import settings_service  # noqa: PLC0415
    from app.tasks.payments import reconcile_escrow_payments  # noqa: PLC0415

    with sf() as db:
        _payment(db)
        settings_service.set_many(db, {"escrow_mode": "live"}, None)
        db.commit()

    with patch("app.core.db.engine", make_engine()):
        result = reconcile_escrow_payments()

    assert result["status"] == "no_provider"
    assert "adapter" in str(result.get("reason", ""))


@requires_real_db
def test_the_beat_runs_the_rules_when_a_client_exists(sf) -> None:  # noqa: ANN001
    from app.models.enums import EscrowStatus  # noqa: PLC0415
    from app.models.payments import EscrowPayment  # noqa: PLC0415
    from app.services import settings_service  # noqa: PLC0415
    from app.tasks.payments import reconcile_escrow_payments  # noqa: PLC0415

    with sf() as db:
        payment, *_ = _payment(db)
        payment_id = payment.id
        settings_service.set_many(db, {"escrow_mode": "live"}, None)
        db.commit()

    bank = _FakeBank({"ESC-1": "funded"})
    with (
        patch("app.core.db.engine", make_engine()),
        patch("app.integrations.escrow.client.get_escrow_client", return_value=bank),
    ):
        result = reconcile_escrow_payments()

    assert result["applied"] == 1
    with sf() as db:
        payment = db.get(EscrowPayment, payment_id)
        assert payment is not None
        assert payment.status == EscrowStatus.funded
