"""
Tests for the "Request an offer" admin-gated brokerage flow.

Layers:
  - OfferRequestCreate schema validation (must carry a quantity or a message).
  - offer_request_service.create_offer_request (only against approved offers).
  - offer_request_service.moderate_offer_request approve/reject + audit.
  - telegram handler _apply_offer_request_moderation idempotency.
  - notify tasks: group review post + seller DM (buyer contact WITHHELD).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests._claims import claim_update

# ── Schema validation ─────────────────────────────────────────────────────────


def test_offer_request_create_requires_qty_or_message() -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from app.schemas.marketplace import OfferRequestCreate  # noqa: PLC0415

    with pytest.raises(ValidationError):
        OfferRequestCreate()  # neither quantity nor message

    # A message alone is fine
    assert OfferRequestCreate(message="Интересует, перезвоните").quantity is None
    # A quantity alone is fine
    assert OfferRequestCreate(quantity=50).qty_unit == "MT"


# ── Service ───────────────────────────────────────────────────────────────────


def test_create_offer_request_rejects_non_approved_offer() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.schemas.marketplace import OfferRequestCreate  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    db = MagicMock()
    # pending offer → not public → ValueError
    offer = SimpleNamespace(id=5, status=SellerOfferStatus.pending_moderation)
    db.query.return_value.filter.return_value.first.return_value = offer
    client = SimpleNamespace(id=1)

    with pytest.raises(ValueError, match="Offer not found"):
        offer_request_service.create_offer_request(
            db, client, 5, OfferRequestCreate(quantity=10)
        )


def test_create_offer_request_blocks_own_offer() -> None:
    """A seller cannot inquire on its own listing (buyer == seller Telegram identity)."""
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.schemas.marketplace import OfferRequestCreate  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    db = MagicMock()
    offer = SimpleNamespace(
        id=5,
        status=SellerOfferStatus.approved,
        seller=SimpleNamespace(telegram_user_id=555),
    )
    db.query.return_value.filter.return_value.first.return_value = offer
    client = SimpleNamespace(id=1, telegram_user_id=555)  # same identity as the seller

    with pytest.raises(ValueError, match="your own offer"):
        offer_request_service.create_offer_request(
            db, client, 5, OfferRequestCreate(quantity=10)
        )
    db.add.assert_not_called()


def test_create_offer_request_allows_other_sellers_offer() -> None:
    """An inquiry on a DIFFERENT seller's approved offer is created normally."""
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.schemas.marketplace import OfferRequestCreate  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    db = MagicMock()
    offer = SimpleNamespace(
        id=5,
        status=SellerOfferStatus.approved,
        seller=SimpleNamespace(telegram_user_id=999),  # a different seller
    )
    db.query.return_value.filter.return_value.first.return_value = offer
    client = SimpleNamespace(id=1, telegram_user_id=555)

    offer_request_service.create_offer_request(db, client, 5, OfferRequestCreate(quantity=10))
    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_moderate_offer_request_approve_sets_forwarded_and_audits() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    req = MagicMock()
    db = MagicMock()
    with patch("app.services.offer_request_service.write_audit") as mock_audit:
        offer_request_service.moderate_offer_request(db, req, 3, approve=True, note=None)

    # The decision is a guarded UPDATE, not a read-then-write (QA #1).
    values, where = claim_update(db, "offer_requests")
    assert values["status"] == OfferRequestStatus.approved
    assert values["reviewed_at"] is not None
    assert values["forwarded_at"] is not None
    assert values["moderated_by"] == 3
    assert OfferRequestStatus.pending in where.values()
    _, kwargs = mock_audit.call_args
    assert kwargs["action"] == "offer_request.approve"


def test_moderate_offer_request_reject_no_forward() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    req = MagicMock()
    db = MagicMock()
    with patch("app.services.offer_request_service.write_audit"):
        offer_request_service.moderate_offer_request(db, req, 3, approve=False, note="dup")

    values, where = claim_update(db, "offer_requests")
    assert values["status"] == OfferRequestStatus.rejected
    assert "forwarded_at" not in values
    assert values["moderation_note"] == "dup"
    assert OfferRequestStatus.pending in where.values()


def test_moderate_offer_request_losing_the_race_raises() -> None:
    """0 rows updated = another reviewer already claimed the inquiry (QA #1)."""
    from app.services import offer_request_service  # noqa: PLC0415

    req = MagicMock()
    db = MagicMock()
    db.execute.return_value.rowcount = 0

    with (
        patch("app.services.offer_request_service.write_audit"),
        pytest.raises(offer_request_service.AlreadyModerated),
    ):
        offer_request_service.moderate_offer_request(db, req, 3, approve=True, note=None)


# ── Telegram handler idempotency ──────────────────────────────────────────────


def _run_apply(status_value: object) -> dict[str, object]:
    from telegram.handlers import moderation  # noqa: PLC0415

    req = MagicMock()
    req.status = status_value
    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("app.services.offer_request_service.moderate_offer_request_via_telegram") as mock_mod,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = None if status_value is None else req
        out = moderation._apply_offer_request_moderation(7, 555, approve=True)
        out["_mod_called"] = mock_mod.called
    return out


def test_apply_offer_request_pending_applies() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415

    out = _run_apply(OfferRequestStatus.pending)
    assert out["ok"] is True
    assert out["_mod_called"] is True


def test_apply_offer_request_already_is_idempotent() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415

    out = _run_apply(OfferRequestStatus.approved)
    assert out["ok"] is False
    assert out["reason"] == "already"
    assert out["_mod_called"] is False


def test_apply_offer_request_missing() -> None:
    out = _run_apply(None)
    assert out["ok"] is False
    assert out["reason"] == "not_found"


# ── Notify tasks ──────────────────────────────────────────────────────────────


def _make_offer_request() -> MagicMock:
    req = MagicMock()
    req.id = 7
    req.company_id = None  # TG-origin (portal-origin shows a 🌐 Портал buyer line)
    req.quantity = 50
    req.qty_unit = "MT"
    req.target_price = 1150
    req.currency = "USD"
    req.message = "Нужно срочно"
    # Edit-tracking defaults (a fresh, never-edited, not-yet-forwarded inquiry).
    req.edited_at = None
    req.seller_notified = False
    req.last_change_summary = None
    req.offer = SimpleNamespace(
        product_id=None,
        product_text="EVA",
        grade_text="Grade A",
        price=1200,
        currency="USD",
        seller=SimpleNamespace(telegram_user_id=999, company_name="Seller LLC"),
    )
    req.client = SimpleNamespace(
        company_name="Buyer LLC", contact_name="Пётр", phone="+998 90 000 00 00", telegram_user_id=555
    )
    return req


def test_send_offer_request_to_group_skipped_when_unset() -> None:
    from app.core.config import settings  # noqa: PLC0415

    with patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", None):
        from app.tasks.notify import send_offer_request_to_group  # noqa: PLC0415

        assert send_offer_request_to_group(offer_request_id=7)["status"] == "skipped"


def test_send_offer_request_to_group_includes_buyer_and_keyboard() -> None:
    sent: list[dict[str, object]] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append({"chat_id": chat_id, "text": text, "reply_markup": kwargs.get("reply_markup")})

    from app.core.config import settings  # noqa: PLC0415

    with (
        patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", -100),
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = _make_offer_request()
        mock_bot.send_message = _capture

        from app.tasks.notify import send_offer_request_to_group  # noqa: PLC0415

        result = send_offer_request_to_group(offer_request_id=7)

    assert result == {"status": "ok", "error": None}
    text = str(sent[0]["text"])
    assert "EVA" in text
    assert "Buyer LLC" in text  # admin sees buyer contact
    assert "Пётр" in text
    assert "🌐 Портал" not in text  # TG-origin inquiry has no portal line (regression)
    assert sent[0]["reply_markup"] is not None  # approve/reject keyboard


def test_send_offer_request_to_group_portal_origin_shows_company() -> None:
    """R2 W4 T4.2 — a portal-originated inquiry card shows the buyer company + origin."""
    sent: list[dict[str, object]] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append({"chat_id": chat_id, "text": text})

    from app.core.config import settings  # noqa: PLC0415
    from app.models.companies import Company  # noqa: PLC0415

    req = _make_offer_request()
    req.company_id = 88
    req.client = None
    company = MagicMock()
    company.short_name = "Buyer Portal Co"
    company.legal_name = "OOO Buyer"
    company.id = 88

    def _get(model, _id):  # noqa: ANN001, ANN202
        return company if model is Company else req

    with (
        patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", -100),
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.side_effect = _get
        mock_bot.send_message = _capture

        from app.tasks.notify import send_offer_request_to_group  # noqa: PLC0415

        result = send_offer_request_to_group(offer_request_id=7)

    assert result == {"status": "ok", "error": None}
    text = str(sent[0]["text"])
    assert "Покупатель (Портал):" in text
    assert "Buyer Portal Co" in text


def test_send_offer_request_to_seller_withholds_buyer_contact() -> None:
    sent: list[dict[str, object]] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append({"chat_id": chat_id, "text": text})

    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = _make_offer_request()
        mock_bot.send_message = _capture

        from app.tasks.notify import send_offer_request_to_seller  # noqa: PLC0415

        result = send_offer_request_to_seller(offer_request_id=7)

    assert result == {"status": "ok", "error": None}
    assert sent[0]["chat_id"] == 999  # seller's telegram id
    text = str(sent[0]["text"])
    assert "EVA" in text
    # 3B: buyer contact must NOT leak to the seller
    assert "Buyer LLC" not in text
    assert "Пётр" not in text
    assert "+998 90 000 00 00" not in text


def test_send_offer_request_to_seller_skipped_without_seller_tg() -> None:
    req = _make_offer_request()
    req.offer = SimpleNamespace(
        product_id=None, product_text="EVA", grade_text=None, price=1200, currency="USD",
        seller=SimpleNamespace(telegram_user_id=None, company_name="X"),
    )

    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = req
        mock_bot.send_message = AsyncMock()

        from app.tasks.notify import send_offer_request_to_seller  # noqa: PLC0415

        result = send_offer_request_to_seller(offer_request_id=7)

    assert result["status"] == "skipped"


# ── Buyer edit: service ───────────────────────────────────────────────────────


def _editable_req(status: object, **overrides: object) -> SimpleNamespace:
    """A minimal editable OfferRequest stand-in for update_offer_request tests."""
    import decimal  # noqa: PLC0415

    base: dict[str, object] = {
        "id": 7,
        "client_id": 1,
        "status": status,
        "quantity": decimal.Decimal("100"),
        "qty_unit": "MT",
        "target_price": decimal.Decimal("1200"),
        "currency": "USD",
        "message": "Старое сообщение",
        "last_change_summary": None,
        "edited_at": None,
        "reviewed_at": "set",
        "moderated_by": 9,
        "moderation_note": "note",
        "forwarded_at": "set",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_offer_request_update_inherits_qty_or_message_rule() -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    from app.schemas.marketplace import OfferRequestUpdate  # noqa: PLC0415

    with pytest.raises(ValidationError):
        OfferRequestUpdate()  # neither quantity nor message
    assert OfferRequestUpdate(quantity=5).qty_unit == "MT"


def test_update_offer_request_records_edit_and_builds_diff() -> None:
    import decimal  # noqa: PLC0415

    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.schemas.marketplace import OfferRequestUpdate  # noqa: PLC0415
    from app.services import offer_request_service as svc  # noqa: PLC0415

    req = _editable_req(OfferRequestStatus.pending)
    db = MagicMock()
    # Full-replacement edit: resend the current values, change only the quantity.
    with patch("app.services.offer_request_service.write_audit") as mock_audit:
        _, changes = svc.update_offer_request(
            db,
            req,
            OfferRequestUpdate(
                quantity=decimal.Decimal("150"),
                qty_unit="MT",
                target_price=decimal.Decimal("1200"),
                currency="USD",
                message="Старое сообщение",
            ),
        )

    assert req.edited_at is not None
    assert req.quantity == decimal.Decimal("150")
    # only the quantity changed → one diff entry with normalized display values
    assert changes == [{"field": "quantity", "old": "100 MT", "new": "150 MT"}]
    assert req.last_change_summary == changes
    _, kwargs = mock_audit.call_args
    assert kwargs["action"] == "offer_request.edit"
    assert kwargs["details"]["via"] == "buyer"


def test_update_offer_request_approved_resets_to_pending() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.schemas.marketplace import OfferRequestUpdate  # noqa: PLC0415
    from app.services import offer_request_service as svc  # noqa: PLC0415

    req = _editable_req(OfferRequestStatus.approved)
    db = MagicMock()
    with patch("app.services.offer_request_service.write_audit"):
        svc.update_offer_request(db, req, OfferRequestUpdate(message="Новое сообщение"))

    assert req.status == OfferRequestStatus.pending  # re-review policy
    assert req.reviewed_at is None
    assert req.moderated_by is None
    assert req.moderation_note is None


def test_update_offer_request_rejected_raises() -> None:
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.schemas.marketplace import OfferRequestUpdate  # noqa: PLC0415
    from app.services import offer_request_service as svc  # noqa: PLC0415

    req = _editable_req(OfferRequestStatus.rejected)
    with pytest.raises(ValueError, match="rejected"):
        svc.update_offer_request(MagicMock(), req, OfferRequestUpdate(message="x"))


def test_update_offer_request_noop_returns_empty() -> None:
    import decimal  # noqa: PLC0415

    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.schemas.marketplace import OfferRequestUpdate  # noqa: PLC0415
    from app.services import offer_request_service as svc  # noqa: PLC0415

    req = _editable_req(OfferRequestStatus.pending)
    with patch("app.services.offer_request_service.write_audit") as mock_audit:
        _, changes = svc.update_offer_request(
            MagicMock(),
            req,
            OfferRequestUpdate(
                quantity=decimal.Decimal("100"),
                qty_unit="MT",
                target_price=decimal.Decimal("1200"),
                currency="USD",
                message="Старое сообщение",
            ),
        )
    assert changes == []
    assert req.edited_at is None  # no-op left untouched
    mock_audit.assert_not_called()


# ── Buyer edit: seller/group notification framing ─────────────────────────────


def test_send_offer_request_to_seller_frames_update_and_clears_diff() -> None:
    sent: list[str] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append(text)

    req = _make_offer_request()
    req.seller_notified = True  # seller has seen a prior version → this DM is an update
    req.last_change_summary = [{"field": "quantity", "old": "100 MT", "new": "150 MT"}]

    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = req
        mock_bot.send_message = _capture

        from app.tasks.notify import send_offer_request_to_seller  # noqa: PLC0415

        result = send_offer_request_to_seller(offer_request_id=7)

    assert result == {"status": "ok", "error": None}
    text = sent[0]
    assert "обновил" in text  # framed as an update, not a new request
    assert "Объём: 100 MT → 150 MT" in text  # shows exactly what changed
    assert "устаревшими" in text  # nudge to review latest
    assert req.last_change_summary is None  # consumed diff cleared
    mock_session.commit.assert_called()


def test_send_offer_request_to_group_edited_shows_diff() -> None:
    sent: list[str] = []

    async def _capture(chat_id: int, text: str, **kwargs: object) -> None:
        sent.append(text)

    from app.core.config import settings  # noqa: PLC0415

    req = _make_offer_request()
    req.edited_at = "2026-07-08T00:00:00Z"  # marks it as an edited re-post
    req.last_change_summary = [{"field": "target_price", "old": "1200 USD", "new": "1100 USD"}]

    with (
        patch.object(settings, "REQUEST_NOTIFY_CHAT_ID", -100),
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("telegram.bot.bot") as mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = req
        mock_bot.send_message = _capture

        from app.tasks.notify import send_offer_request_to_group  # noqa: PLC0415

        result = send_offer_request_to_group(offer_request_id=7)

    assert result == {"status": "ok", "error": None}
    text = sent[0]
    assert "Обновлённый запрос" in text  # edited header
    assert "Желаемая цена: 1200 USD → 1100 USD" in text
