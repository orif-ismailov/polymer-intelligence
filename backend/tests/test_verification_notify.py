"""send_verification_case_to_group task tests (R1 W6 — T6.1).

Consumer registration + skip/never-raise DB-free; the actual card send (bot patched)
against test_polymer (guarded).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    migrate_head,
    requires_real_db,
    session_factory,
)


def test_consumer_registered_for_case_submitted() -> None:
    import app.tasks.notify as notify  # noqa: PLC0415
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    assert notify.send_verification_case_to_group in CONSUMERS[event_types.VERIFICATION_CASE_SUBMITTED]


def test_skips_when_no_chat_configured(monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", None)
    monkeypatch.setattr(settings, "REQUEST_NOTIFY_CHAT_ID", None)
    assert notify.send_verification_case_to_group(aggregate_id="1")["status"] == "skipped"


def test_skips_when_no_case_id() -> None:
    from app.tasks import notify  # noqa: PLC0415

    assert notify.send_verification_case_to_group()["status"] == "skipped"


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
def test_sends_card_with_keyboard(engine: sa.Engine, sf, monkeypatch) -> None:  # noqa: ANN001
    from app.core.config import settings  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, "+998900000001")
        company = company_service.create_company(db, account, "UZ", "123456789")
        company.short_name = "ShortCo"
        verification_service.open_case(db, company)
        monkeypatch.setattr(verification_service, "_dispatch_checks", lambda case_id: None)
        case = verification_service.submit_case(db, company, account)
        db.commit()
        case_id = case.id

    monkeypatch.setattr("app.core.db.engine", engine)  # task uses Session(engine)
    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", -100123)
    send_message = AsyncMock()
    monkeypatch.setattr("telegram.bot.bot.send_message", send_message)

    result = notify.send_verification_case_to_group(aggregate_id=str(case_id))
    assert result["status"] == "ok"
    send_message.assert_awaited_once()
    kwargs = send_message.await_args.kwargs
    assert kwargs["chat_id"] == -100123
    assert "ShortCo" in kwargs["text"]
    assert "123456789" in kwargs["text"]  # INN
    assert kwargs["reply_markup"] is not None  # the approve/reject/info keyboard


@requires_real_db
def test_missing_case_returns_error_without_raising(engine: sa.Engine, sf, monkeypatch) -> None:  # noqa: ANN001, ARG001
    from app.core.config import settings  # noqa: PLC0415
    from app.tasks import notify  # noqa: PLC0415

    monkeypatch.setattr("app.core.db.engine", engine)
    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", -100123)
    monkeypatch.setattr("telegram.bot.bot.send_message", AsyncMock())
    assert notify.send_verification_case_to_group(aggregate_id="999999")["status"] == "error"
