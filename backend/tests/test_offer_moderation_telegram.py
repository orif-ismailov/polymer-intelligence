"""
Tests for approving/rejecting a seller offer from the team Telegram group.

Two layers:
  - offer_service.moderate_offer_via_telegram — the DB effect + audit (actor is a
    Telegram user, so moderated_by stays NULL and the id lands in audit details).
  - telegram.handlers.moderation._apply_moderation — the sync transaction the callback
    handler runs: applies the decision only while the offer is still pending
    (idempotency), and reports not_found / already for the other cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests._claims import claim_update


def test_moderate_via_telegram_approve_sets_public_and_audits() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import offer_service  # noqa: PLC0415

    offer = MagicMock()
    # No chemistry on this offer: a bare MagicMock would answer "yes" to having
    # a substance and the compliance re-check would compare two mocks (P5).
    offer.substance_id = None
    offer.cas_number = None
    offer.hs_code = None
    db = MagicMock()

    with patch("app.services.offer_service.write_audit") as mock_audit:
        offer_service.moderate_offer_via_telegram(db, offer, 555, approve=True)

    # The decision is a guarded UPDATE, not a read-then-write (QA #1): the SET
    # publishes, the WHERE is what makes it exactly-once.
    values, where = claim_update(db, "seller_offers")
    assert values["status"] == SellerOfferStatus.approved
    assert values["published_at"] is not None
    assert SellerOfferStatus.pending_moderation in where.values()
    # Never commits — the caller owns the transaction.
    db.commit.assert_not_called()
    # actor is a telegram user → no staff id, id recorded in details
    _, kwargs = mock_audit.call_args
    assert kwargs["staff_user_id"] is None
    assert kwargs["action"] == "offer.approve"
    assert kwargs["details"]["telegram_user_id"] == 555


def test_moderate_via_telegram_reject_sets_rejected() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import offer_service  # noqa: PLC0415

    offer = MagicMock()
    db = MagicMock()

    with patch("app.services.offer_service.write_audit"):
        offer_service.moderate_offer_via_telegram(db, offer, 555, approve=False, note="spam")

    values, where = claim_update(db, "seller_offers")
    assert values["status"] == SellerOfferStatus.rejected
    assert values["moderation_note"] == "spam"
    assert SellerOfferStatus.pending_moderation in where.values()


def test_moderate_via_telegram_losing_the_race_raises() -> None:
    """0 rows updated = another decision already claimed the offer (QA #1)."""
    import pytest  # noqa: PLC0415

    from app.services import offer_service  # noqa: PLC0415

    offer = MagicMock()
    db = MagicMock()
    db.execute.return_value.rowcount = 0

    with (
        patch("app.services.offer_service.write_audit"),
        pytest.raises(offer_service.AlreadyModerated),
    ):
        offer_service.moderate_offer_via_telegram(db, offer, 555, approve=False)


def test_apply_moderation_reports_already_when_the_claim_loses() -> None:
    """A stale pre-check must not become a second verdict — the tap reports 'already'."""
    from telegram.handlers import moderation  # noqa: PLC0415

    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.services import offer_service  # noqa: PLC0415

    offer = MagicMock()
    offer.status = SellerOfferStatus.pending_moderation  # stale read: it just left

    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch(
            "app.services.offer_service.moderate_offer_via_telegram",
            side_effect=offer_service.AlreadyModerated(11, "approved"),
        ),
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = offer

        result = moderation._apply_moderation(11, 555, approve=True)

        assert mock_session.commit.called is False
        assert mock_session.rollback.called is True

    assert result == {"ok": False, "reason": "already", "status": "approved"}


def _run_apply(offer_status: object, *, approve: bool = True) -> dict[str, object]:
    """Drive _apply_moderation with a mocked session whose get() returns a stub offer."""
    from telegram.handlers import moderation  # noqa: PLC0415

    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    offer = MagicMock()
    offer.status = offer_status

    with (
        patch("sqlalchemy.orm.Session") as mock_session_cls,
        patch("app.core.db.engine"),
        patch("app.services.offer_service.moderate_offer_via_telegram") as mock_moderate,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = None if offer_status is None else offer

        result = moderation._apply_moderation(11, 555, approve=approve)
        result["_moderate_called"] = mock_moderate.called
        result["_committed"] = mock_session.commit.called
    _ = SellerOfferStatus  # keep import used
    return result


def test_apply_moderation_pending_applies_and_commits() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    result = _run_apply(SellerOfferStatus.pending_moderation, approve=True)
    assert result["ok"] is True
    assert result["approved"] is True
    assert result["_moderate_called"] is True
    assert result["_committed"] is True


def test_apply_moderation_already_decided_is_idempotent() -> None:
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415

    result = _run_apply(SellerOfferStatus.approved)
    assert result["ok"] is False
    assert result["reason"] == "already"
    assert result["_moderate_called"] is False


def test_apply_moderation_missing_offer() -> None:
    result = _run_apply(None)
    assert result["ok"] is False
    assert result["reason"] == "not_found"
