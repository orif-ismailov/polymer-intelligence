"""Telegram verification-moderation handler tests (R1 W6 — T6.2).

Callback authz + idempotency are DB-free (mocked CallbackQuery); the _apply_decision
DB transaction (approve/reject/request-info + AlreadyDecided) runs against test_polymer.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa

from tests._verification_db import (
    clean,
    make_account,
    make_engine,
    make_staff,  # noqa: F401 — kept for parity with other suites
    migrate_head,
    requires_real_db,
    session_factory,
)

# ── callback authz + idempotency (DB-free) ────────────────────────────────────


def _callback(data: str = "vercase:approve:5", chat_id: int = 123) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 555
    cb.from_user.full_name = "Admin"
    cb.from_user.username = "admin"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.chat.id = chat_id
    cb.message.text = "🔎 Заявка"
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    return cb


def test_callback_denied_from_wrong_chat(monkeypatch) -> None:  # noqa: ANN001
    from telegram.handlers import verification as vh  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    monkeypatch.setattr(settings, "VERIFICATION_NOTIFY_CHAT_ID", 123)
    monkeypatch.setattr(settings, "REQUEST_NOTIFY_CHAT_ID", None)
    cb = _callback(chat_id=999)  # not the verification group
    asyncio.run(vh.on_verification_moderation(cb))
    cb.answer.assert_any_call("Недоступно", show_alert=True)


def test_callback_idempotent_already_decided(monkeypatch) -> None:  # noqa: ANN001
    from telegram.handlers import verification as vh  # noqa: PLC0415

    monkeypatch.setattr(vh, "_require_verification_admin", AsyncMock(return_value=True))
    monkeypatch.setattr(vh, "_apply_decision", MagicMock(return_value={"ok": False, "reason": "already"}))
    cb = _callback()
    asyncio.run(vh.on_verification_moderation(cb))
    cb.answer.assert_any_call("Уже обработано", show_alert=True)
    cb.message.edit_reply_markup.assert_awaited_once()


def test_callback_success_edits_message(monkeypatch) -> None:  # noqa: ANN001
    from telegram.handlers import verification as vh  # noqa: PLC0415

    monkeypatch.setattr(vh, "_require_verification_admin", AsyncMock(return_value=True))
    monkeypatch.setattr(vh, "_apply_decision", MagicMock(return_value={"ok": True, "action": "approve"}))
    cb = _callback()
    asyncio.run(vh.on_verification_moderation(cb))
    cb.message.edit_text.assert_awaited_once()
    assert "✅ Одобрено" in cb.message.edit_text.await_args.kwargs["text"]


def test_callback_bad_data_is_noop(monkeypatch) -> None:  # noqa: ANN001, ARG001
    from telegram.handlers import verification as vh  # noqa: PLC0415

    cb = _callback(data="vercase:bogus:5")
    asyncio.run(vh.on_verification_moderation(cb))
    cb.answer.assert_awaited_once_with()  # plain ack, no decision


# ── _apply_decision DB transaction (real DB) ──────────────────────────────────


@pytest.fixture(scope="module")
def engine() -> sa.Engine:
    migrate_head()
    return make_engine()


@pytest.fixture
def sf(engine: sa.Engine):  # noqa: ANN201
    clean(engine)
    yield session_factory(engine)
    clean(engine)


def _pending_review(sf, monkeypatch, phone: str, tax: str) -> tuple[int, int]:  # noqa: ANN001
    from app.domains.verification import service as verification_service  # noqa: PLC0415
    from app.domains.verification.models import VerificationCheck  # noqa: PLC0415
    from app.models.enums import VerificationCheckStatus, VerificationCheckType  # noqa: PLC0415
    from app.services import company_service  # noqa: PLC0415

    with sf() as db:
        account = make_account(db, phone)
        company = company_service.create_company(db, account, "UZ", tax)
        verification_service.open_case(db, company)
        monkeypatch.setattr(verification_service, "_dispatch_checks", lambda case_id: None)
        case = verification_service.submit_case(db, company, account)
        for check in db.query(VerificationCheck).filter(VerificationCheck.case_id == case.id):
            if check.check_type != VerificationCheckType.manual_kyb:
                check.status = VerificationCheckStatus.passed
        db.flush()
        verification_service.on_check_completed(db, case.id)
        db.commit()
        return company.id, case.id


@requires_real_db
def test_apply_decision_approve_verifies_company(engine: sa.Engine, sf, monkeypatch) -> None:  # noqa: ANN001
    from telegram.handlers.verification import _apply_decision  # noqa: PLC0415

    from app.models.companies import Company  # noqa: PLC0415
    from app.models.enums import CompanyStatus  # noqa: PLC0415

    company_id, case_id = _pending_review(sf, monkeypatch, "+998900000001", "123456789")
    monkeypatch.setattr("app.core.db.engine", engine)

    result = _apply_decision(case_id, 555, "approve")
    assert result == {"ok": True, "action": "approve"}
    with sf() as db:
        assert db.get(Company, company_id).status == CompanyStatus.verified

    # a second decision is idempotent (already left pending_review)
    assert _apply_decision(case_id, 555, "approve") == {"ok": False, "reason": "already"}


@requires_real_db
def test_apply_decision_request_info(engine: sa.Engine, sf, monkeypatch) -> None:  # noqa: ANN001
    from telegram.handlers.verification import _apply_decision  # noqa: PLC0415

    from app.domains.verification.models import VerificationCase  # noqa: PLC0415
    from app.models.enums import VerificationCaseStatus  # noqa: PLC0415

    _company_id, case_id = _pending_review(sf, monkeypatch, "+998900000002", "222222222")
    monkeypatch.setattr("app.core.db.engine", engine)

    assert _apply_decision(case_id, 555, "info")["ok"] is True
    with sf() as db:
        case = db.get(VerificationCase, case_id)
        assert case.status == VerificationCaseStatus.needs_info
        assert case.decision_note == "Требуется дополнительная информация"


@requires_real_db
def test_apply_decision_missing_case(engine: sa.Engine, sf, monkeypatch) -> None:  # noqa: ANN001, ARG001
    from telegram.handlers.verification import _apply_decision  # noqa: PLC0415

    monkeypatch.setattr("app.core.db.engine", engine)
    assert _apply_decision(999999, 555, "approve") == {"ok": False, "reason": "not_found"}
