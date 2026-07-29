"""
Offer-moderation callback handler — approve/reject a seller offer from the team group.

When a seller submits a new offer, notify.send_offer_to_group posts it to the team
Telegram group (image + seller details) with an inline keyboard carrying
callback_data ``offer:<action>:<id>`` (see telegram/bot.offer_moderation_keyboard).
This router handles the tap: it authorizes the presser, applies the same moderation
decision the dashboard makes, and edits the message to record the outcome.

Authorization (defense in depth):
  1. The callback must originate from the configured REQUEST_NOTIFY_CHAT_ID group.
  2. The presser must be an administrator/creator of that group.
Any other user gets a "not allowed" toast and no state change.

Idempotency: an offer that has already left `pending_moderation` (e.g. decided on the
dashboard, or a double-tap) is not re-moderated — the buttons are dropped and the
presser is told it was already handled.

Import-safety: like the notify tasks, all backend imports are deferred into the
handler body so importing this module under pytest opens no socket and needs no DB.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.core.config import settings

logger = logging.getLogger(__name__)

offer_moderation_router = Router()

_ADMIN_STATUSES = ("administrator", "creator")


def _apply_moderation(offer_id: int, telegram_user_id: int, *, approve: bool) -> dict[str, Any]:
    """Synchronous DB transaction: moderate the offer if still pending.

    Returns a small result dict:
      {"ok": True, "approved": bool}                    — decision applied
      {"ok": False, "reason": "not_found"}              — no such offer
      {"ok": False, "reason": "already", "status": str} — already moderated
    Run via asyncio.to_thread so the webhook event loop is never blocked.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.models.enums import SellerOfferStatus  # noqa: PLC0415
    from app.models.marketplace import SellerOffer  # noqa: PLC0415
    from app.services import offer_service  # noqa: PLC0415

    with Session(engine) as session:
        offer = session.get(SellerOffer, offer_id)
        if offer is None:
            return {"ok": False, "reason": "not_found"}
        if offer.status != SellerOfferStatus.pending_moderation:
            return {"ok": False, "reason": "already", "status": offer.status.value}
        try:
            offer_service.moderate_offer_via_telegram(
                session, offer, telegram_user_id, approve=approve
            )
        except offer_service.AlreadyModerated as exc:
            # The status read above went stale between the check and the write —
            # a dashboard moderator (or the other inline button) got there first.
            # The service's claim is what actually decides; this is just how the
            # tap is reported.
            session.rollback()
            return {"ok": False, "reason": "already", "status": exc.current_status}
        session.commit()
        return {"ok": True, "approved": approve}


async def _require_group_admin(callback: CallbackQuery) -> bool:
    """Return True iff the tap came from an admin of the configured team group.

    Answers the callback with a toast on any failure and returns False. Shared by the
    offer and offer-request moderation handlers.
    """
    from telegram.bot import bot  # noqa: PLC0415

    message = callback.message
    chat_id = message.chat.id if message is not None else None
    user_id = callback.from_user.id

    if settings.REQUEST_NOTIFY_CHAT_ID is None or chat_id != settings.REQUEST_NOTIFY_CHAT_ID:
        await callback.answer("Недоступно", show_alert=True)
        return False

    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as exc:  # noqa: BLE001 — never crash the webhook on a Telegram API hiccup
        logger.warning("moderation.authz_check_failed", extra={"error": str(exc)})
        await callback.answer("Не удалось проверить права", show_alert=True)
        return False

    if member.status not in _ADMIN_STATUSES:
        await callback.answer("Только администраторы могут модерировать", show_alert=True)
        return False
    return True


async def _finish_moderation_message(
    callback: CallbackQuery, *, approve: bool, approved_label: str, rejected_label: str
) -> None:
    """Edit the group message to record the outcome + who decided, and drop buttons."""
    message = callback.message
    who = callback.from_user.full_name or callback.from_user.username or str(callback.from_user.id)
    verdict = approved_label if approve else rejected_label
    suffix = f"\n\n{verdict} · {who}"
    if message is not None:
        try:
            if message.caption is not None:
                await message.edit_caption(caption=(message.caption + suffix)[:1024], reply_markup=None)
            elif message.text is not None:
                await message.edit_text(text=(message.text + suffix)[:4096], reply_markup=None)
            else:
                await message.edit_reply_markup(reply_markup=None)
        except Exception as exc:  # noqa: BLE001 — the decision is already committed
            logger.warning("moderation.message_edit_failed", extra={"error": str(exc)})


@offer_moderation_router.callback_query(F.data.startswith("offer:"))
async def on_offer_moderation(callback: CallbackQuery) -> None:
    """Handle an ✅/❌ tap on a pending-offer group message."""
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "offer":
        await callback.answer()
        return
    _, action, offer_id_raw = parts
    try:
        offer_id = int(offer_id_raw)
    except ValueError:
        await callback.answer()
        return

    if not await _require_group_admin(callback):
        return

    user_id = callback.from_user.id
    approve = action == "approve"
    result = await asyncio.to_thread(
        _apply_moderation, offer_id, user_id, approve=approve
    )

    if not result["ok"]:
        if result.get("reason") == "already":
            await callback.answer("Предложение уже обработано", show_alert=True)
            if callback.message is not None:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("offer_moderation.markup_clear_failed", extra={"error": str(exc)})
        else:
            await callback.answer("Предложение не найдено", show_alert=True)
        return

    await _finish_moderation_message(
        callback, approve=approve, approved_label="✅ Подтверждено", rejected_label="❌ Отклонено"
    )
    await callback.answer("Подтверждено" if approve else "Отклонено")
    logger.info(
        "offer_moderation.done",
        extra={"offer_id": offer_id, "approve": approve, "telegram_user_id": user_id},
    )


def _apply_offer_request_moderation(
    offer_request_id: int, telegram_user_id: int, *, approve: bool
) -> dict[str, Any]:
    """Synchronous DB transaction: moderate a buyer inquiry if still pending.

    Mirrors _apply_moderation. Returns {"ok": True, "approved": bool} on success, or
    {"ok": False, "reason": "not_found" | "already"}.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.models.enums import OfferRequestStatus  # noqa: PLC0415
    from app.models.marketplace import OfferRequest  # noqa: PLC0415
    from app.services import offer_request_service  # noqa: PLC0415

    with Session(engine) as session:
        req = session.get(OfferRequest, offer_request_id)
        if req is None:
            return {"ok": False, "reason": "not_found"}
        if req.status != OfferRequestStatus.pending:
            return {"ok": False, "reason": "already", "status": req.status.value}
        try:
            offer_request_service.moderate_offer_request_via_telegram(
                session, req, telegram_user_id, approve=approve
            )
        except offer_request_service.AlreadyModerated as exc:
            # Same race as the offer path: the pre-check is a courtesy, the
            # service's claim is the guarantee.
            session.rollback()
            return {"ok": False, "reason": "already", "status": exc.current_status}
        session.commit()
        return {"ok": True, "approved": approve}


@offer_moderation_router.callback_query(F.data.startswith("offreq:"))
async def on_offer_request_moderation(callback: CallbackQuery) -> None:
    """Handle an ✅/❌ tap on a pending buyer-inquiry group message."""
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "offreq":
        await callback.answer()
        return
    _, action, raw_id = parts
    try:
        offer_request_id = int(raw_id)
    except ValueError:
        await callback.answer()
        return

    if not await _require_group_admin(callback):
        return

    user_id = callback.from_user.id
    approve = action == "approve"
    result = await asyncio.to_thread(
        _apply_offer_request_moderation, offer_request_id, user_id, approve=approve
    )

    if not result["ok"]:
        if result.get("reason") == "already":
            await callback.answer("Запрос уже обработан", show_alert=True)
            if callback.message is not None:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("offer_request_moderation.markup_clear_failed", extra={"error": str(exc)})
        else:
            await callback.answer("Запрос не найден", show_alert=True)
        return

    # Approved → forward the inquiry to the seller (buyer contact withheld).
    if approve:
        from app.services import offer_request_service  # noqa: PLC0415

        offer_request_service.enqueue_offer_request_to_seller(offer_request_id)

    await _finish_moderation_message(
        callback, approve=approve, approved_label="✅ Одобрено", rejected_label="❌ Отклонено"
    )
    await callback.answer("Одобрено" if approve else "Отклонено")
    logger.info(
        "offer_request_moderation.done",
        extra={"offer_request_id": offer_request_id, "approve": approve, "telegram_user_id": user_id},
    )
