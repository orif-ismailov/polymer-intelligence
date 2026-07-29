"""
`send_lab_order_to_group` (P6 W6 — T6.1).

The card that starts the manual process. Nobody is watching the dashboard queue
at 9pm, and the whole feature depends on an operator picking up the phone — so
submission is the one lab event that reaches the staff group. The statuses after
it are moved by the same person already looking at the queue.

Registration + skip/never-raise are DB-free; the send (bot patched) runs against
test_polymer (guarded).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_company,
    make_engine,
    make_seller_offer,
    migrate_head,
    requires_real_db,
    session_factory,
)


def test_consumer_registered_for_lab_order_submitted() -> None:
    import app.tasks.notify as notify  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    assert notify.send_lab_order_to_group in CONSUMERS[event_types.LAB_ORDER_SUBMITTED]


def test_only_submission_gets_a_card() -> None:
    """Completion rings the customer's bell, not the staff group: by then the
    operator is the one who uploaded the passport."""
    import app.tasks.notify as notify  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    assert notify.send_lab_order_to_group not in CONSUMERS.get(
        event_types.LAB_ORDER_COMPLETED, []
    )


def test_skips_when_no_chat_configured(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", None)
    monkeypatch.setattr(settings, "REQUEST_NOTIFY_CHAT_ID", None)
    assert notify.send_lab_order_to_group(aggregate_id="1")["status"] == "skipped"


def test_skips_when_no_order_id() -> None:
    from app.tasks import notify  # noqa: PLC0415

    assert notify.send_lab_order_to_group()["status"] == "skipped"


def test_never_raises_on_a_missing_order(monkeypatch) -> None:  # noqa: ANN001
    """Fail-soft: a card that throws would have the dispatcher retry forever."""
    from app.core.config import settings  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", -1000)
    result = notify.send_lab_order_to_group(aggregate_id="999999")
    assert result["status"] in {"error", "ok"}


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
def test_sends_a_card_naming_the_customer_and_the_subject(
    engine: sa.Engine, sf, monkeypatch
) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.services import lab_service  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    monkeypatch.setattr("app.core.db.engine", engine)  # the task uses Session(engine)
    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", -1000)
    sent = AsyncMock()
    monkeypatch.setattr("telegram.bot.bot.send_message", sent)

    with sf() as db:
        owner = make_account(db, "+998900000701")
        company = make_company(db, owner, tax_id="300000701", legal_name="OOO ЛабКлиент")
        offer = make_seller_offer(db, company=company, product_text="PP H030")
        order = lab_service.create_order(
            db,
            company=company,
            account=owner,
            offer=offer,
            sample_volume="2 кг",
            comment="проверить ПТР",
        )
        db.commit()
        order_id, number = order.id, order.number

    result = notify.send_lab_order_to_group(aggregate_id=str(order_id))
    assert result["status"] == "ok", result.get("error")
    sent.assert_awaited_once()
    text = sent.await_args.kwargs["text"]
    # Everything an operator needs before dialling a laboratory.
    assert number in text
    assert "OOO ЛабКлиент" in text
    assert "2 кг" in text
    assert "проверить ПТР" in text
