"""Verification-case moderation callback handler (R1 W6 — T6.2).

When a company submits a verification case, notify.send_verification_case_to_group
posts it to the team group with an inline keyboard carrying callback_data
``vercase:<action>:<id>`` (see telegram/bot.verification_moderation_keyboard). This
router handles the tap: authorize the presser, apply the same decision the dashboard
makes (as a Telegram actor — staff_user_id=None, telegram id in the audit), and edit
the message to record the outcome.

Authorization mirrors offer moderation: the tap must come from the configured
verification group (VERIFICATION_NOTIFY_CHAT_ID, else REQUEST_NOTIFY_CHAT_ID) and the
presser must be an admin/creator of it. Idempotent: a case already decided (dashboard,
double-tap) → the buttons drop and the presser is told "уже обработано". A case that has
not REACHED `pending_review` is a different refusal and gets a different answer — it keeps
its buttons, because it may still become decidable.

Import-safety: backend imports are deferred into the handler body so importing this
module under pytest opens no socket and needs no DB.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.core.config import settings

logger = logging.getLogger(__name__)

verification_moderation_router = Router()

_ADMIN_STATUSES = ("administrator", "creator")
_DEFAULT_INFO_NOTE = "Требуется дополнительная информация"
_OUTCOME_LABELS = {
    "approve": "✅ Одобрено",
    "reject": "❌ Отклонено",
    "info": "✋ Запрошена информация",
}

#: Case statuses a decision can never be taken from again. Plain strings, so this
#: module still needs no backend model import at import time.
_TERMINAL_STATUSES = frozenset({"approved", "rejected", "cancelled"})

#: Why a case that is not `pending_review` cannot be decided yet. The buttons stay
#: on the message: unlike a decided case, this one may well become decidable.
_NOT_PENDING_ANSWERS = {
    "needs_info": "Кейс возвращён клиенту на доработку — решать пока нечего",
    "draft": "Заявка ещё не отправлена на проверку",
    "submitted": "Автопроверки ещё не завершены",
    "checks_running": "Автопроверки ещё не завершены",
}
_NOT_PENDING_FALLBACK = "Кейс сейчас не готов к решению"


def _notify_chat_id() -> int | None:
    return settings.VERIFICATION_NOTIFY_CHAT_ID or settings.REQUEST_NOTIFY_CHAT_ID


async def _require_verification_admin(callback: CallbackQuery) -> bool:
    """True iff the tap came from an admin of the configured verification group."""
    from telegram.bot import bot  # noqa: PLC0415

    message = callback.message
    chat_id = message.chat.id if message is not None else None
    user_id = callback.from_user.id

    allowed = _notify_chat_id()
    if allowed is None or chat_id != allowed:
        await callback.answer("Недоступно", show_alert=True)
        return False

    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as exc:  # noqa: BLE001 — never crash the webhook on a Telegram hiccup
        logger.warning("verification_moderation.authz_check_failed", extra={"error": str(exc)})
        await callback.answer("Не удалось проверить права", show_alert=True)
        return False

    if member.status not in _ADMIN_STATUSES:
        await callback.answer("Только администраторы могут решать", show_alert=True)
        return False
    return True


def _apply_decision(case_id: int, telegram_user_id: int, action: str) -> dict[str, Any]:
    """Synchronous DB transaction: apply the case decision if still pending_review."""
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.verification.models import VerificationCase  # noqa: PLC0415
    from app.domains.verification import service as verification_service  # noqa: PLC0415

    with Session(engine) as session:
        case = session.get(VerificationCase, case_id)
        if case is None:
            return {"ok": False, "reason": "not_found"}
        actor = {"telegram_user_id": telegram_user_id}
        try:
            if action == "approve":
                verification_service.approve(session, case, staff_user_id=None, actor=actor)
            elif action == "reject":
                verification_service.reject(session, case, staff_user_id=None, actor=actor)
            else:  # info
                verification_service.request_info(
                    session, case, staff_user_id=None, actor=actor, note=_DEFAULT_INFO_NOTE
                )
        except verification_service.AlreadyDecided:
            # That exception conflates "a colleague got there first" with "this
            # case never reached pending_review". Answering «Уже обработано» to
            # the second sends someone hunting for the person who handled it —
            # read the status back and say which one it actually is.
            session.refresh(case)
            case_status = str(case.status)
            return {
                "ok": False,
                "reason": "already" if case_status in _TERMINAL_STATUSES else "not_pending_review",
                "case_status": case_status,
            }
        session.commit()
        return {"ok": True, "action": action}


@verification_moderation_router.callback_query(F.data.startswith("vercase:"))
async def on_verification_moderation(callback: CallbackQuery) -> None:
    """Handle an ✅/❌/✋ tap on a submitted-case group message."""
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[0] != "vercase" or parts[1] not in ("approve", "reject", "info"):
        await callback.answer()
        return
    action = parts[1]
    try:
        case_id = int(parts[2])
    except ValueError:
        await callback.answer()
        return

    if not await _require_verification_admin(callback):
        return

    user_id = callback.from_user.id
    result = await asyncio.to_thread(_apply_decision, case_id, user_id, action)

    if not result["ok"]:
        reason = result.get("reason")
        if reason == "already":
            await callback.answer("Уже обработано", show_alert=True)
            if callback.message is not None:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("verification_moderation.markup_clear_failed", extra={"error": str(exc)})
        elif reason == "not_pending_review":
            # Keep the keyboard — this case may reach pending_review later, and
            # dropping the buttons would strip the group of the way to act then.
            await callback.answer(
                _NOT_PENDING_ANSWERS.get(str(result.get("case_status")), _NOT_PENDING_FALLBACK),
                show_alert=True,
            )
        else:
            await callback.answer("Заявка не найдена", show_alert=True)
        return

    who = callback.from_user.full_name or callback.from_user.username or str(user_id)
    suffix = f"\n\n{_OUTCOME_LABELS[action]} · {who}"
    message = callback.message
    if message is not None:
        try:
            if message.text is not None:
                await message.edit_text(text=(message.text + suffix)[:4096], reply_markup=None)
            else:
                await message.edit_reply_markup(reply_markup=None)
        except Exception as exc:  # noqa: BLE001 — the decision is already committed
            logger.warning("verification_moderation.edit_failed", extra={"error": str(exc)})

    await callback.answer(_OUTCOME_LABELS[action].split(" ", 1)[1])
    logger.info(
        "verification_moderation.done",
        extra={"case_id": case_id, "action": action, "telegram_user_id": user_id},
    )
