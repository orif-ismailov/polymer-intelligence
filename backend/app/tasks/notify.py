"""
Notify Celery tasks module.

Tasks:
  check_source_health — scans all enabled sources for 3-strike failures (≤30 min SLA).
  send_status_change_notification — pushes D-10 localized status update to client via bot.
  send_delivery — dispatches a team alert to per-rule chat_ids via the aiogram bot
                  (REQ-bot-team / FR-16). Queue: notify (same queue — token-bucket
                  rate limiter applies: 25 msg/s bot, 1 msg/s chat_id per D-09).

check_source_health:
  Supersedes the placeholder in tasks/placeholders.py (same task name; last
  registration wins during autodiscovery — Celery resolves by name, not by module).
  Beat schedule: crontab(minute="*/5") → every 5 minutes.

  Security:
    T-02-20: alert deduplication via source_health_service.raise_source_failure_alert
             (ON CONFLICT DO NOTHING on dedupe_key) — no alert storm.
    T-02-22: defense in depth for the ≤30 min guarantee (independent scan).

send_status_change_notification:
  Sends a localized D-10 status push to the client via the Telegram bot.
  Queue: notify (≤30 s delivery SLA for REQ-nfr-performance).

  Security:
    T-03-12: deep-link button targets recipient's own request — no cross-client leak.
    T-03-13: task never raises — always returns error dict so the worker stays alive.

send_delivery:
  Dispatches an Alert's body to each per-rule delivery channel (chat_id) via
  the existing aiogram bot singleton, on the same notify queue.
  Token-bucket rate limit (25 msg/s global bot, 1 msg/s per chat_id) is enforced
  by dispatching through the notify Celery queue with per-task sleep(1/25).
  Task never raises (T-03-13 pattern): returns error dict on any failure so the
  worker stays alive.

  Security:
    T-04-26: Dedupe handled upstream (evaluate_alert_rules); this task only sends
             what is in the deliveries table for the given alert_id.
    D-09: All team alert deliveries reuse the Phase-3 notify queue — token-bucket
          rate limiter already in this path; DO NOT create a separate queue (Pitfall 7).
"""

from __future__ import annotations

import asyncio
import html
import logging
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _deliver_to_group(
    bot: Any,
    chat_id: int,
    thread_id: int | None,
    *,
    text: str | None = None,
    photo: Any = None,
    caption: str | None = None,
    reply_markup: Any = None,
) -> None:
    """Send a group notification, optionally into a forum topic (message_thread_id).

    Routes into `thread_id` when set. If the topic is invalid/closed (Telegram
    returns a 400 — TelegramBadRequest), the message is re-sent to the group's
    General topic instead of being silently dropped. Network/other errors propagate
    to the caller's task-level handler (which logs + returns an error dict).
    """
    from aiogram.exceptions import TelegramBadRequest  # noqa: PLC0415

    async def _send(with_thread: bool) -> None:
        extra: dict[str, Any] = {}
        if with_thread and thread_id is not None:
            extra["message_thread_id"] = thread_id
        if photo is not None:
            await bot.send_photo(
                chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup, **extra
            )
        else:
            await bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup, **extra
            )

    try:
        await _send(True)
    except TelegramBadRequest as exc:
        if thread_id is None:
            raise
        logger.warning(
            "notify.topic_fallback_to_general",
            extra={"chat_id": chat_id, "thread_id": thread_id, "error": str(exc)},
        )
        await _send(False)


# ── D-10 localized client-facing status labels ────────────────────────────────
# CLIENT_STATUS_MAP (request_service.py) maps internal RequestStatus → display key.
# These dicts map that display key → localized human-readable label for bot pushes.
# New language: add a new dict below and wire it in _localized_status_label().

_RU_STATUS_LABELS: dict[str, str] = {
    "new": "Новая заявка",
    "in_review": "На рассмотрении",
    "offer_received": "Предложение получено",
    "matched": "Подобрано",
    "closed": "Закрыта",
    "cancelled": "Отменена",
}

_UZ_STATUS_LABELS: dict[str, str] = {
    "new": "Yangi ariza",
    "in_review": "Ko'rib chiqilmoqda",
    "offer_received": "Taklif olindi",
    "matched": "Topildi",
    "closed": "Yopildi",
    "cancelled": "Bekor qilindi",
}

_TR_STATUS_LABELS: dict[str, str] = {
    "new": "Yeni talep",
    "in_review": "İnceleniyor",
    "offer_received": "Teklif alındı",
    "matched": "Eşleştirildi",
    "closed": "Kapatıldı",
    "cancelled": "İptal edildi",
}

_LANG_LABEL_MAP: dict[str, dict[str, str]] = {
    "ru": _RU_STATUS_LABELS,
    "uz": _UZ_STATUS_LABELS,
    "tr": _TR_STATUS_LABELS,
}


def _localized_status_label(lang: str, display_key: str) -> str:
    """Return the localized D-10 label for the given display key and language.

    Falls back to 'ru' if the language is not in _LANG_LABEL_MAP.
    Falls back to the display_key itself if the key is not in the label dict.
    """
    labels = _LANG_LABEL_MAP.get(lang, _RU_STATUS_LABELS)
    return labels.get(display_key, display_key)


@celery_app.task(name="check_source_health")  # type: ignore[untyped-decorator]
def check_source_health() -> dict[str, Any]:
    """Scan all enabled sources and raise deduped source_failure alerts for any with >= 3 failures.

    Supersedes the placeholder in tasks/placeholders.py.
    Scheduled by beat: every 5 minutes.

    This is the safety net for REQ-nfr-reliability SC#5:
    - Guarantees that a source_failure alert is visible within 30 minutes
      even if the inline raise inside record_fetch_failure was missed.
    - Idempotent: safe to run repeatedly; alerts are deduped per source per day.

    Returns:
        A dict with keys: status, scanned_count (int), error (str | None)
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.services.source_health_service import check_all_sources_health  # noqa: PLC0415

    logger.info("check_source_health.start")

    try:
        with Session(engine) as session:
            check_all_sources_health(session)
            session.commit()
    except Exception as exc:
        logger.error("check_source_health.error", extra={"error": str(exc)})
        return {"status": "error", "error": str(exc)}

    logger.info("check_source_health.done")
    return {"status": "ok", "error": None}


@celery_app.task(name="send_status_change_notification", queue="notify")  # type: ignore[untyped-decorator]
def send_status_change_notification(request_id: int) -> dict[str, Any]:
    """Push a localized D-10 status update to the client via the Telegram bot.

    Queue: notify (≤30 s delivery SLA for REQ-nfr-performance / SC#3).

    Loads the Request + its Client from the database, picks the client's language
    (ru/uz), maps the internal RequestStatus to a D-10 display key via
    client_facing_status(), resolves the localized label, renders the
    telegram/templates/{lang}/status_change.txt template, and sends a message
    to the client via the aiogram Bot with a deep-link WebApp inline button.

    Security:
      T-03-12: deep-link button targets recipient's own request ID — the Web App
               route /requests/{id} is IDOR-scoped by initData (03-02 T-03-07),
               so even a guessed ID returns 404 for non-owners.
      T-03-13: task wrapped in try/except — never raises, returns error dict so
               the Celery worker stays alive.

    Args:
        request_id: Primary key of the requests table row.

    Returns:
        {"status": "ok", "error": None} on success.
        {"status": "error", "error": str} on any failure (task never raises).
    """
    # All imports are lazy (inside the body) per DEC-lazy-notify-import:
    # - avoids circular imports at module level
    # - keeps module import socket-free (pytest collection safe)
    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot, load_template  # noqa: PLC0415

    from app.core.config import settings as _settings  # noqa: PLC0415
    from app.core.db import engine  # noqa: PLC0415
    from app.models.requests import Request  # noqa: PLC0415
    from app.services.request_service import client_facing_status  # noqa: PLC0415

    logger.info("notify.status_change.start", extra={"request_id": request_id})

    try:
        with Session(engine) as session:
            request = session.get(Request, request_id)

            if request is None:
                logger.warning(
                    "notify.status_change.not_found",
                    extra={"request_id": request_id},
                )
                return {"status": "error", "error": f"Request {request_id} not found"}

            client = request.client
            if client is None:
                # Portal-origin request (R2, A2): no TG client to DM. W2 routes
                # these to a portal_notification instead; nothing to send here.
                logger.info(
                    "notify.status_change.no_client",
                    extra={"request_id": request_id},
                )
                return {"status": "ok", "error": None}
            lang = client.language if client.language in ("ru", "uz") else "ru"

            # Resolve D-10 display key → localized label
            display_key = client_facing_status(request.status)
            status_label = _localized_status_label(lang, display_key)

            # Render the status_change template
            text = load_template(lang, "status_change").format(
                number=request.number,
                status_label=status_label,
            )

            # Build deep-link inline keyboard button (T-03-12: own request only)
            from aiogram.types import (  # noqa: PLC0415
                InlineKeyboardButton,
                InlineKeyboardMarkup,
                WebAppInfo,
            )

            # The Mini App is served at the root of ai-imex.com; it uses HashRouter,
            # so the request detail is at /#/requests/{id}.
            deep_link_url = (
                f"{_settings.PUBLIC_WEBAPP_URL.rstrip('/')}/#/requests/{request.id}"
            )
            open_label = "Открыть заявку" if lang == "ru" else "Arizani ochish"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=open_label,
                            web_app=WebAppInfo(url=deep_link_url) if _settings.PUBLIC_WEBAPP_URL else None,
                            url=deep_link_url if not _settings.PUBLIC_WEBAPP_URL else None,
                        )
                    ]
                ]
            )

            # Send the push only if the client has a telegram_user_id
            if client.telegram_user_id is not None:
                asyncio.run(
                    bot.send_message(
                        chat_id=client.telegram_user_id,
                        text=text,
                        reply_markup=keyboard,
                    )
                )
                logger.info(
                    "notify.status_change.sent",
                    extra={
                        "request_id": request_id,
                        "telegram_user_id": client.telegram_user_id,
                        "lang": lang,
                        "status_label": status_label,
                    },
                )
            else:
                logger.warning(
                    "notify.status_change.no_telegram_user_id",
                    extra={"request_id": request_id, "client_id": client.id},
                )
            # MR-01: no session.commit() — this task only reads from the DB.
            # The `with Session(engine) as session:` block closes (not commits) on exit.

    except Exception as exc:
        logger.error(
            "notify.status_change.error",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return {"status": "error", "error": str(exc)}

    logger.info("notify.status_change.done", extra={"request_id": request_id})
    return {"status": "ok", "error": None}


# ── Token-bucket helpers (D-09 / REQ-bot-team) ────────────────────────────────
# Telegram rate limits: 25 messages/s global bot limit, 1 message/s per chat_id.
# Since send_delivery is called per alert (not per message), and each alert may
# have multiple deliveries, we sleep between individual message sends to stay
# within the per-chat 1 msg/s limit. The global 25 msg/s limit is handled by
# the Celery worker concurrency (max 25 concurrent tasks on the notify queue).
# References: D-09, Pitfall 7 — do NOT create a separate queue.

_BOT_GLOBAL_INTERVAL_S = 1.0 / 25  # 25 msg/s = 40 ms between messages


@celery_app.task(name="send_delivery", queue="notify")  # type: ignore[untyped-decorator]
def send_delivery(alert_id: int) -> dict[str, Any]:
    """Dispatch a team alert to all its delivery channel recipients via the Telegram bot.

    Loads the Alert and its Delivery rows from the database, then sends
    alert.title + alert.body to each chat_id via the existing aiogram Bot.
    Respects the Telegram rate limits (D-09):
      - global bot limit: 25 messages/s (sleep between sends)
      - per-chat limit: 1 message/s (1 alert per rule+entity per chat; dedupe upstream)

    Queue: notify (same as send_status_change_notification — rate limiter is in
    this path; do NOT move to a separate queue per Pitfall 7).

    Security:
      T-04-26: Dedupe handled by evaluate_alert_rules (ON CONFLICT dedupe_key);
               this task sends whatever is in deliveries for the given alert.
      T-03-13 pattern: task never raises — returns error dict on any failure
               so the Celery worker stays alive.

    Args:
        alert_id: Primary key of the alerts table row.

    Returns:
        {"status": "ok", "sent": N, "error": None} on success (N = messages sent).
        {"status": "error", "sent": 0, "error": str} on failure.
    """
    # All imports are lazy (inside the body) per DEC-lazy-notify-import:
    # - avoids circular imports at module level
    # - keeps module import socket-free (pytest collection safe)
    import time  # noqa: PLC0415

    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.models.alerts import Alert, Delivery  # noqa: PLC0415
    from app.models.enums import DeliveryChannel, DeliveryStatus  # noqa: PLC0415

    logger.info("notify.send_delivery.start", extra={"alert_id": alert_id})

    try:
        with Session(engine) as session:
            alert = session.get(Alert, alert_id)

            if alert is None:
                logger.warning(
                    "notify.send_delivery.not_found",
                    extra={"alert_id": alert_id},
                )
                return {"status": "error", "sent": 0, "error": f"Alert {alert_id} not found"}

            # Load all queued deliveries for this alert
            deliveries = (
                session.query(Delivery)
                .filter(
                    Delivery.alert_id == alert_id,
                    Delivery.status == DeliveryStatus.queued,
                )
                .all()
            )

            if not deliveries:
                logger.info(
                    "notify.send_delivery.no_queued_deliveries",
                    extra={"alert_id": alert_id},
                )
                return {"status": "ok", "sent": 0, "error": None}

            # WR-04: HTML-escape dynamic title/body before embedding in <b>…</b> tags
            # so that alert content containing "<", ">", "&" doesn't malform the Telegram
            # HTML message (e.g. "PP > 1000 MT" would otherwise break the markup).
            safe_title = html.escape(alert.title)
            safe_body = html.escape(alert.body)
            message_text = f"<b>{safe_title}</b>\n\n{safe_body}"
            sent_count = 0

            for delivery in deliveries:
                # Only dispatch Telegram DM / channel deliveries
                if delivery.channel not in (
                    DeliveryChannel.telegram_dm,
                    DeliveryChannel.telegram_channel,
                ):
                    logger.debug(
                        "notify.send_delivery.non_telegram_skip",
                        extra={"delivery_id": delivery.id, "channel": delivery.channel},
                    )
                    continue

                try:
                    chat_id_str = delivery.recipient
                    # chat_id may be a negative group/channel ID or positive user DM ID
                    chat_id = int(chat_id_str)

                    asyncio.run(
                        bot.send_message(
                            chat_id=chat_id,
                            text=message_text,
                            parse_mode="HTML",  # WR-04: render <b> tags; without this they appear as literal text
                        )
                    )

                    # Mark delivery as sent
                    delivery.status = DeliveryStatus.sent
                    import datetime  # noqa: PLC0415
                    delivery.sent_at = datetime.datetime.now(tz=datetime.UTC)
                    sent_count += 1

                    logger.info(
                        "notify.send_delivery.sent",
                        extra={"alert_id": alert_id, "chat_id": chat_id},
                    )

                    # Token-bucket: respect global 25 msg/s rate limit (D-09)
                    time.sleep(_BOT_GLOBAL_INTERVAL_S)

                except Exception as exc:
                    logger.error(
                        "notify.send_delivery.send_error",
                        extra={"alert_id": alert_id, "delivery_id": delivery.id, "error": str(exc)},
                    )
                    delivery.status = DeliveryStatus.failed
                    delivery.error = str(exc)

            session.commit()

    except Exception as exc:
        logger.error(
            "notify.send_delivery.error",
            extra={"alert_id": alert_id, "error": str(exc)},
        )
        return {"status": "error", "sent": 0, "error": str(exc)}

    logger.info("notify.send_delivery.done", extra={"alert_id": alert_id, "sent": sent_count})
    return {"status": "ok", "sent": sent_count, "error": None}


# ── New-request team notification (sales group) ───────────────────────────────

_URGENCY_RU: dict[str, str] = {
    "high": "Срочно (1–3 дня)",
    "medium": "В течение недели/месяца",
    "low": "Под заказ (14–25 дней)",
}


@celery_app.task(name="send_request_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_request_to_group(request_id: int) -> dict[str, Any]:
    """Post a new buyer request to the team Telegram group (REQUEST_NOTIFY_CHAT_ID).

    Best-effort, read-only. No-ops (status="skipped") when the chat id is unset.
    Never raises — broker/bot/network failures are logged and returned as an error
    dict so request creation is never affected.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot  # noqa: PLC0415

    from app.core.config import settings as _settings  # noqa: PLC0415
    from app.core.db import engine  # noqa: PLC0415
    from app.models.reference import Product  # noqa: PLC0415
    from app.models.requests import Request  # noqa: PLC0415

    chat_id = _settings.REQUEST_NOTIFY_CHAT_ID
    if chat_id is None:
        return {"status": "skipped", "error": "REQUEST_NOTIFY_CHAT_ID not set"}

    logger.info("notify.request_to_group.start", extra={"request_id": request_id})

    try:
        with Session(engine) as session:
            request = session.get(Request, request_id)
            if request is None:
                return {"status": "error", "error": f"Request {request_id} not found"}

            product_name: str | None = None
            if request.product_id is not None:
                product = session.get(Product, request.product_id)
                product_name = product.name_ru if product else None
            product_label = product_name or request.product_text or "—"

            lines: list[str] = [f"🆕 Новая заявка {request.number}", ""]
            # Origin line for portal-originated requests (R2 W4 T4.2); TG requests
            # keep the card byte-identical (no line added).
            if request.company_id is not None:
                from app.domains.companies.models import Company  # noqa: PLC0415

                company = session.get(Company, request.company_id)
                if company is not None:
                    cname = company.short_name or company.legal_name or f"#{company.id}"
                    lines.append(f"🌐 Портал: {cname}")
                    lines.append("")
            grade = f" · {request.grade_text}" if request.grade_text else ""
            lines.append(f"📦 Продукт: {product_label}{grade}")
            if request.volume is not None:
                lines.append(f"📊 Объём: {request.volume} {request.volume_unit}")
            if request.target_price is not None:
                lines.append(f"💰 Целевая цена: {request.target_price} {request.currency}")
            if request.port_or_city:
                lines.append(f"📍 Город: {request.port_or_city}")
            if request.urgency is not None:
                urgency_key = getattr(request.urgency, "value", str(request.urgency))
                lines.append(f"⏱ Срочность: {_URGENCY_RU.get(urgency_key, urgency_key)}")

            contact: list[str] = []
            if request.company_name:
                contact.append(f"🏢 {request.company_name}")
            if request.contact_name:
                contact.append(f"👤 {request.contact_name}")
            if request.phone:
                contact.append(f"📞 {request.phone}")
            if contact:
                lines.append("")
                lines.extend(contact)
            if request.comment:
                lines.append("")
                lines.append(f"💬 {request.comment}")

            asyncio.run(
                _deliver_to_group(
                    bot, chat_id, _settings.NOTIFY_TOPIC_BUYERS, text="\n".join(lines)
                )
            )
            logger.info(
                "notify.request_to_group.sent",
                extra={"request_id": request_id, "chat_id": chat_id, "number": request.number},
            )
    except Exception as exc:
        logger.error(
            "notify.request_to_group.error",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return {"status": "error", "error": str(exc)}

    return {"status": "ok", "error": None}


# ── New-offer team notification (marketplace moderation) ──────────────────────

_AVAILABILITY_RU: dict[str, str] = {
    "in_stock": "В наличии",
    "on_order": "Под заказ",
}


@celery_app.task(name="send_offer_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_offer_to_group(offer_id: int, edited: bool = False) -> dict[str, Any]:
    """Post a seller offer to the team Telegram group for moderation.

    The message carries the product info, the seller's own contact details, and (when
    present) the offer's first image as a photo. An inline keyboard with
    ✅ Подтвердить / ❌ Отклонить lets a group admin approve or reject the offer from
    Telegram (telegram/handlers/moderation.py applies the same decision the dashboard
    moderation queue does).

    When ``edited`` is True the offer is re-entering moderation after a seller revised it
    (a previously-approved/rejected listing), so the header signals a re-review rather
    than a brand-new listing.

    Best-effort and read-only: no-ops (status="skipped") when the chat id is unset;
    never raises — bot/broker/storage failures are logged and returned as an error dict
    so nothing upstream is affected.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot, offer_moderation_keyboard  # noqa: PLC0415

    from app.core.config import settings as _settings  # noqa: PLC0415
    from app.core.db import engine  # noqa: PLC0415
    from app.domains.marketplace.models import SellerOffer  # noqa: PLC0415
    from app.models.enums import OfferFileKind  # noqa: PLC0415
    from app.models.reference import Product  # noqa: PLC0415

    chat_id = _settings.REQUEST_NOTIFY_CHAT_ID
    if chat_id is None:
        return {"status": "skipped", "error": "REQUEST_NOTIFY_CHAT_ID not set"}

    logger.info("notify.offer_to_group.start", extra={"offer_id": offer_id})

    try:
        with Session(engine) as session:
            offer = session.get(SellerOffer, offer_id)
            if offer is None:
                return {"status": "error", "error": f"Offer {offer_id} not found"}

            seller = offer.seller

            product_name: str | None = None
            if offer.product_id is not None:
                product = session.get(Product, offer.product_id)
                product_name = product.name_ru if product else None
            product_label = product_name or offer.product_text or "—"

            header = (
                "✏️ Обновлённое предложение на модерацию"
                if edited
                else "🆕 Новое предложение на модерацию"
            )
            lines: list[str] = [header, ""]
            grade = f" · {offer.grade_text}" if offer.grade_text else ""
            lines.append(f"📦 Продукт: {product_label}{grade}")
            if offer.polymer_type:
                lines.append(f"🧪 Тип: {offer.polymer_type}")
            availability_key = getattr(offer.availability, "value", str(offer.availability))
            lines.append(f"🔖 {_AVAILABILITY_RU.get(availability_key, availability_key)}")
            # «Под заказ» offers carry no fixed qty/price — price is "по запросу".
            if offer.qty_available is not None:
                lines.append(f"📊 Объём: {offer.qty_available} {offer.qty_unit}")
            incoterms = getattr(offer.incoterms, "value", str(offer.incoterms))
            if offer.price is not None:
                lines.append(f"💰 Цена: {offer.price} {offer.currency} ({incoterms})")
            else:
                lines.append(f"💰 Цена: по запросу ({incoterms})")
            if offer.min_order_qty is not None:
                lines.append(f"📦 Мин. партия: {offer.min_order_qty} {offer.qty_unit}")
            if offer.warehouse_city:
                lines.append(f"📍 Склад: {offer.warehouse_city}")
            if offer.description:
                lines.append("")
                lines.append(f"💬 {offer.description}")

            # Who created it — the detail the team needs to vet the listing. Dual-origin
            # (R1 W5): a company-origin offer (seller is None) renders the verified company
            # instead of the Telegram seller contact block.
            contact: list[str] = []
            if offer.company_id is not None:
                if offer.display_name:
                    contact.append(f"🏢 {offer.display_name}")
                contact.append(f"🏛 Компания{' ✅' if offer.company_verified else ''}")
            elif seller is not None:
                if seller.company_name:
                    contact.append(f"🏢 {seller.company_name}")
                if seller.contact_name:
                    contact.append(f"👤 {seller.contact_name}")
                if seller.phone:
                    contact.append(f"📞 {seller.phone}")
                if seller.telegram_username:
                    contact.append(f"✈️ @{seller.telegram_username}")
                if seller.telegram_user_id is not None:
                    contact.append(f"🆔 {seller.telegram_user_id}")
            if contact:
                lines.append("")
                lines.append("Продавец:")
                lines.extend(contact)

            text = "\n".join(lines)
            keyboard = offer_moderation_keyboard(offer.id)

            # First image file, if any → send as a photo with the text as caption.
            image = next(
                (f for f in offer.files if f.kind == OfferFileKind.image and f.storage_path),
                None,
            )
            image_bytes: bytes | None = None
            if image is not None and image.storage_path:
                try:
                    from app.core.storage import s3_client  # noqa: PLC0415

                    obj = s3_client.get_object(  # type: ignore[attr-defined]
                        Bucket=_settings.S3_BUCKET, Key=image.storage_path
                    )
                    image_bytes = obj["Body"].read()
                except Exception as exc:  # noqa: BLE001 — fall back to a text-only message
                    logger.warning(
                        "notify.offer_to_group.image_fetch_failed",
                        extra={"offer_id": offer_id, "error": str(exc)},
                    )

            if image_bytes is not None:
                from aiogram.types import BufferedInputFile  # noqa: PLC0415

                photo = BufferedInputFile(
                    image_bytes, filename=(image.file_name if image else None) or "offer.jpg"
                )
                # Photo captions are capped at 1024 chars by Telegram.
                asyncio.run(
                    _deliver_to_group(
                        bot,
                        chat_id,
                        _settings.NOTIFY_TOPIC_SELLERS,
                        photo=photo,
                        caption=text[:1024],
                        reply_markup=keyboard,
                    )
                )
            else:
                asyncio.run(
                    _deliver_to_group(
                        bot,
                        chat_id,
                        _settings.NOTIFY_TOPIC_SELLERS,
                        text=text,
                        reply_markup=keyboard,
                    )
                )

            logger.info(
                "notify.offer_to_group.sent",
                extra={"offer_id": offer_id, "chat_id": chat_id, "with_image": image_bytes is not None},
            )
    except Exception as exc:
        logger.error(
            "notify.offer_to_group.error",
            extra={"offer_id": offer_id, "error": str(exc)},
        )
        return {"status": "error", "error": str(exc)}

    return {"status": "ok", "error": None}


# ── Offer-request ("Request an offer") notifications ──────────────────────────


def _offer_product_label(session: object, offer: Any) -> str:
    """Resolve a human product label for an offer (product name, else free text)."""
    from app.models.reference import Product  # noqa: PLC0415

    if offer.product_id is not None:
        product = session.get(Product, offer.product_id)  # type: ignore[attr-defined]
        if product is not None:
            return str(product.name_ru)
    return offer.product_text or "—"


_OFFER_REQUEST_FIELD_RU: dict[str, str] = {
    "quantity": "Объём",
    "target_price": "Желаемая цена",
    "message": "Сообщение",
}


def _render_offer_request_changes(summary: Any) -> list[str]:
    """Render a buyer-edit diff (offer_request.last_change_summary) as bullet lines.

    Returns [] when there is no summary. Each entry becomes "• Label: old → new".
    """
    lines: list[str] = []
    for change in summary or []:
        if not isinstance(change, dict):
            continue
        field = change.get("field", "")
        label = _OFFER_REQUEST_FIELD_RU.get(field, field or "—")
        old = change.get("old") or "—"
        new = change.get("new") or "—"
        lines.append(f"• {label}: {old} → {new}")
    return lines


@celery_app.task(name="send_offer_request_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_offer_request_to_group(offer_request_id: int) -> dict[str, Any]:
    """Post a new buyer inquiry to the team group for review, with ✅/❌ buttons.

    Shows the inquiry (product, requested qty, target price, message), the buyer's
    contact (staff-only), and which offer/seller it targets. A group admin approves
    (→ forward to seller) or rejects from chat. Best-effort; never raises.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot, offer_request_moderation_keyboard  # noqa: PLC0415

    from app.core.config import settings as _settings  # noqa: PLC0415
    from app.core.db import engine  # noqa: PLC0415
    from app.domains.marketplace.models import OfferRequest  # noqa: PLC0415

    chat_id = _settings.REQUEST_NOTIFY_CHAT_ID
    if chat_id is None:
        return {"status": "skipped", "error": "REQUEST_NOTIFY_CHAT_ID not set"}

    logger.info("notify.offer_request_to_group.start", extra={"offer_request_id": offer_request_id})

    try:
        with Session(engine) as session:
            req = session.get(OfferRequest, offer_request_id)
            if req is None:
                return {"status": "error", "error": f"OfferRequest {offer_request_id} not found"}

            offer = req.offer
            product_label = _offer_product_label(session, offer)
            grade = f" · {offer.grade_text}" if offer.grade_text else ""

            # An edited inquiry (edited_at set) is re-posted for re-review with a diff.
            edited = getattr(req, "edited_at", None) is not None
            header = "✏️ Обновлённый запрос предложения" if edited else "🛒 Новый запрос предложения"
            lines: list[str] = [header, ""]
            lines.append(f"📦 Товар: {product_label}{grade}")
            if offer.price is not None:
                lines.append(f"💵 Цена в объявлении: {offer.price} {offer.currency}")
            else:
                lines.append("💵 Цена в объявлении: по запросу")
            if req.quantity is not None:
                lines.append(f"📊 Нужный объём: {req.quantity} {req.qty_unit}")
            if req.target_price is not None:
                cur = req.currency or offer.currency
                lines.append(f"🎯 Желаемая цена: {req.target_price} {cur}")
            if req.message:
                lines.append("")
                lines.append(f"💬 {req.message}")

            if edited:
                changes = _render_offer_request_changes(req.last_change_summary)
                if changes:
                    lines.append("")
                    lines.append("Что изменилось:")
                    lines.extend(changes)

            client = req.client
            buyer: list[str] = []
            buyer_label = "Покупатель:"
            if req.company_id is not None:
                # Portal-origin inquiry (R2 W4 T4.2): show the buyer company + origin.
                from app.domains.companies.models import Company  # noqa: PLC0415

                company = session.get(Company, req.company_id)
                if company is not None:
                    cname = company.short_name or company.legal_name or f"#{company.id}"
                    buyer.append(f"🌐 Портал · {cname}")
                buyer_label = "Покупатель (Портал):"
            elif client is not None:
                if client.company_name:
                    buyer.append(f"🏢 {client.company_name}")
                if client.contact_name:
                    buyer.append(f"👤 {client.contact_name}")
                if client.phone:
                    buyer.append(f"📞 {client.phone}")
                if client.telegram_user_id is not None:
                    buyer.append(f"🆔 {client.telegram_user_id}")
            if buyer:
                lines.append("")
                lines.append(buyer_label)
                lines.extend(buyer)

            keyboard = offer_request_moderation_keyboard(req.id)
            asyncio.run(
                _deliver_to_group(
                    bot,
                    chat_id,
                    _settings.NOTIFY_TOPIC_BUYERS,
                    text="\n".join(lines),
                    reply_markup=keyboard,
                )
            )
            logger.info(
                "notify.offer_request_to_group.sent",
                extra={"offer_request_id": offer_request_id, "chat_id": chat_id},
            )
    except Exception as exc:
        logger.error(
            "notify.offer_request_to_group.error",
            extra={"offer_request_id": offer_request_id, "error": str(exc)},
        )
        return {"status": "error", "error": str(exc)}

    return {"status": "ok", "error": None}


@celery_app.task(name="send_offer_request_to_seller", queue="notify")  # type: ignore[untyped-decorator]
def send_offer_request_to_seller(offer_request_id: int) -> dict[str, Any]:
    """DM an APPROVED inquiry to the seller — WITHOUT the buyer's contact.

    The team stays the intermediary (3B): the seller learns a buyer is interested and
    the commercial terms, then coordinates with the team. Best-effort; never raises.
    Skips (status="skipped") when the seller has no telegram_user_id.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.marketplace.models import OfferRequest  # noqa: PLC0415

    logger.info("notify.offer_request_to_seller.start", extra={"offer_request_id": offer_request_id})

    try:
        with Session(engine) as session:
            req = session.get(OfferRequest, offer_request_id)
            if req is None:
                return {"status": "error", "error": f"OfferRequest {offer_request_id} not found"}

            offer = req.offer
            seller = offer.seller
            if seller is None or seller.telegram_user_id is None:
                logger.warning(
                    "notify.offer_request_to_seller.no_seller_tg",
                    extra={"offer_request_id": offer_request_id},
                )
                return {"status": "skipped", "error": "seller has no telegram_user_id"}

            product_label = _offer_product_label(session, offer)
            grade = f" · {offer.grade_text}" if offer.grade_text else ""

            # If the seller has already seen this inquiry, frame this DM as an UPDATE
            # (the buyer revised it) and show exactly what changed.
            is_update = bool(getattr(req, "seller_notified", False))
            if is_update:
                lines = ["✏️ Покупатель обновил свой запрос!", "", f"📦 Товар: {product_label}{grade}"]
                changes = _render_offer_request_changes(getattr(req, "last_change_summary", None))
                if changes:
                    lines.append("")
                    lines.append("Что изменилось:")
                    lines.extend(changes)
            else:
                lines = ["📩 Новый запрос на ваше предложение!", "", f"📦 Товар: {product_label}{grade}"]

            if req.quantity is not None:
                lines.append(f"📊 Нужный объём: {req.quantity} {req.qty_unit}")
            if req.target_price is not None:
                cur = req.currency or offer.currency
                lines.append(f"🎯 Желаемая цена: {req.target_price} {cur}")
            if req.message:
                lines.append("")
                lines.append(f"💬 {req.message}")
            lines.append("")
            if is_update:
                lines.append(
                    "Пожалуйста, ознакомьтесь с обновлёнными условиями, чтобы не работать "
                    "с устаревшими данными."
                )
            else:
                lines.append("С вами свяжется наш менеджер для деталей.")

            asyncio.run(bot.send_message(chat_id=seller.telegram_user_id, text="\n".join(lines)))

            # Record the seller has now seen it (so a later edit is framed as an update)
            # and clear the consumed diff.
            req.seller_notified = True
            req.last_change_summary = None
            session.commit()

            logger.info(
                "notify.offer_request_to_seller.sent",
                extra={
                    "offer_request_id": offer_request_id,
                    "seller_tg": seller.telegram_user_id,
                    "update": is_update,
                },
            )
    except Exception as exc:
        logger.error(
            "notify.offer_request_to_seller.error",
            extra={"offer_request_id": offer_request_id, "error": str(exc)},
        )
        return {"status": "error", "error": str(exc)}

    return {"status": "ok", "error": None}


# ── OTP / portal SMS delivery (R1 W3) ─────────────────────────────────────────


def _write_sms_log(
    phone: str,
    purpose: str,
    provider: str,
    provider_msg_id: str | None,
    status: str,
) -> None:
    """Record one SMS attempt in `sms_send_log` (separate short transaction).

    Codes are NEVER written here — only the fact/outcome of a send, for cost
    tracking + OTP-abuse forensics. Best-effort: a logging failure must not fail
    the send task.
    """
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.models.accounts import SmsSendLog  # noqa: PLC0415

    try:
        with SessionLocal() as db:
            db.add(
                SmsSendLog(
                    phone=phone,
                    purpose=purpose,
                    provider=provider,
                    provider_msg_id=provider_msg_id,
                    status=status,
                )
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 — forensic log must not break delivery
        logger.warning("sms_log.error", extra={"error": str(exc)})


@celery_app.task(name="send_sms", queue="notify")  # type: ignore[untyped-decorator]
def send_sms(phone: str, text: str, purpose: str = "otp") -> dict[str, Any]:
    """Deliver an SMS via the configured provider and log the attempt.

    Never raises (T-03-13 pattern): returns a status dict so the worker stays
    alive on any provider/DB failure. The OTP code lives in `text` and is NEVER
    logged here — only the console driver prints it (dev/CI, gated by
    SMS_PROVIDER=console).
    """
    from app.integrations.sms import get_sms_provider  # noqa: PLC0415

    provider = get_sms_provider()
    try:
        result = asyncio.run(provider.send(phone, text))
    except Exception as exc:  # noqa: BLE001 — dead provider must not kill the worker
        logger.warning("send_sms.error", extra={"phone": phone, "error": str(exc)})
        _write_sms_log(phone, purpose, provider.provider_name, None, "error")
        return {"status": "error", "error": str(exc)}

    outcome = "ok" if result.ok else "error"
    _write_sms_log(phone, purpose, provider.provider_name, result.provider_msg_id, outcome)
    return {"status": outcome, "provider_msg_id": result.provider_msg_id, "error": result.error}


# ── Verification case → team group card (R1 W6) ───────────────────────────────

_CHECK_STATUS_EMOJI: dict[str, str] = {
    "passed": "✅",
    "warning": "⚠️",
    "failed": "❌",
    "pending": "⏳",
    "running": "⏳",
    "waived": "➖",
    "unavailable": "🚫",
}


def _verification_notify_chat_id() -> int | None:
    """Verification cards go to VERIFICATION_NOTIFY_CHAT_ID, else the request group."""
    from app.core.config import settings  # noqa: PLC0415

    return settings.VERIFICATION_NOTIFY_CHAT_ID or settings.REQUEST_NOTIFY_CHAT_ID


@celery_app.task(name="send_verification_case_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_verification_case_to_group(
    event_id: int | None = None,
    aggregate_id: str | None = None,
    payload: Any = None,
) -> dict[str, Any]:
    """Post a submitted verification case to the team group for a human decision.

    Consumer of VERIFICATION_CASE_SUBMITTED (called with event_id/aggregate_id/payload;
    aggregate_id is the case id). Skips when no group is configured. Never raises
    (T-03-13): returns a status dict so the worker stays alive.
    """
    case_id_raw = aggregate_id or (payload or {}).get("case_id")
    if case_id_raw is None:
        return {"status": "skipped", "error": "no_case_id"}
    case_id = int(case_id_raw)

    chat_id = _verification_notify_chat_id()
    if chat_id is None:
        return {"status": "skipped", "error": "no_chat_id"}

    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot, verification_moderation_keyboard  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.verification.models import (
        VerificationCase,
        VerificationCheck,
        VerificationDocument,
    )

    try:
        with Session(engine) as session:
            case = session.get(VerificationCase, case_id)
            if case is None:
                return {"status": "error", "error": f"case {case_id} not found"}
            company = session.get(Company, case.company_id)
            checks = (
                session.query(VerificationCheck)
                .filter(VerificationCheck.case_id == case_id)
                .order_by(VerificationCheck.id)
                .all()
            )
            doc_count = (
                session.query(VerificationDocument)
                .filter(VerificationDocument.company_id == case.company_id)
                .count()
            )

            name = None
            roles: list[str] = []
            tax_id = ""
            if company is not None:
                name = company.short_name or company.legal_name
                tax_id = company.tax_id
                roles = [r.role.value for r in company.business_roles]

            lines = ["🔎 Новая заявка на верификацию", ""]
            lines.append(f"🏢 {name or ('ИНН ' + tax_id)}")
            lines.append(f"🆔 ИНН: {tax_id}")
            lines.append(f"📋 Роли: {', '.join(roles) if roles else '—'}")
            lines.append(f"📎 Документы: {doc_count}")
            if checks:
                lines.append("")
                lines.append("Проверки:")
                for check in checks:
                    status_value = check.status.value
                    emoji = _CHECK_STATUS_EMOJI.get(status_value, "•")
                    lines.append(f"{emoji} {check.check_type.value}: {status_value}")

            asyncio.run(
                bot.send_message(
                    chat_id=chat_id,
                    text="\n".join(lines)[:4096],
                    reply_markup=verification_moderation_keyboard(case_id),
                )
            )
    except Exception as exc:  # noqa: BLE001 — a bot/DB hiccup must not kill the worker
        logger.error("notify.verification_case.error", extra={"case_id": case_id, "error": str(exc)})
        return {"status": "error", "error": str(exc)}

    logger.info("notify.verification_case.sent", extra={"case_id": case_id, "chat_id": chat_id})
    return {"status": "ok", "error": None}


@celery_app.task(name="send_contract_activated_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_contract_activated_to_group(
    event_id: int | None = None,
    aggregate_id: str | None = None,
    payload: Any = None,
) -> dict[str, Any]:
    """Read-only staff awareness card when a contract is signed by both sides.

    Consumer of CONTRACT_ACTIVATED (aggregate_id = contract id). No buttons — R3 has
    no staff mutation of contracts. Trilingual (ru/uz/tr). Never raises.
    """
    contract_id_raw = aggregate_id or (payload or {}).get("contract_id")
    if contract_id_raw is None:
        return {"status": "skipped", "error": "no_contract_id"}
    contract_id = int(contract_id_raw)

    chat_id = _verification_notify_chat_id()
    if chat_id is None:
        return {"status": "skipped", "error": "no_chat_id"}

    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.contracts.models import Contract  # noqa: PLC0415

    def _name(session: Any, company_id: int) -> str:  # noqa: ANN401
        c = session.get(Company, company_id)
        return (c.legal_name or c.short_name or c.tax_id) if c is not None else str(company_id)

    try:
        with Session(engine) as session:
            contract = session.get(Contract, contract_id)
            if contract is None:
                return {"status": "error", "error": f"contract {contract_id} not found"}
            initiator = _name(session, contract.initiator_company_id)
            counterparty = _name(session, contract.counterparty_company_id)
            lines = [
                "✅ Договор подписан обеими сторонами"
                " · Shartnoma ikkala tomon tomonidan imzolandi"
                " · Sözleşme iki tarafça imzalandı",
                "",
                f"📄 {contract.title}",
                f"🏢 {initiator} → {counterparty}",
                f"🆔 {contract.public_id}",
            ]
            asyncio.run(bot.send_message(chat_id=chat_id, text="\n".join(lines)[:4096]))
    except Exception as exc:  # noqa: BLE001 — a bot/DB hiccup must not kill the worker
        logger.error("notify.contract_activated.error", extra={"contract_id": contract_id, "error": str(exc)})
        return {"status": "error", "error": str(exc)}

    logger.info("notify.contract_activated.sent", extra={"contract_id": contract_id, "chat_id": chat_id})
    return {"status": "ok", "error": None}


def _deal_card(deal_id_raw: str | None, headline: str, extra: list[str] | None = None) -> dict[str, Any]:
    """Send a read-only deal card to the staff group. Never raises."""
    if deal_id_raw is None:
        return {"status": "skipped", "error": "no_deal_id"}
    try:
        deal_id = int(deal_id_raw)
    except (TypeError, ValueError):
        return {"status": "skipped", "error": "bad_deal_id"}

    chat_id = _verification_notify_chat_id()
    if chat_id is None:
        return {"status": "skipped", "error": "no_chat_id"}

    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.domains.deals.models import Deal  # noqa: PLC0415

    def _name(session: Any, company_id: int) -> str:  # noqa: ANN401
        company = session.get(Company, company_id)
        return (
            (company.legal_name or company.short_name or company.tax_id)
            if company is not None
            else str(company_id)
        )

    try:
        with Session(engine) as session:
            deal = session.get(Deal, deal_id)
            if deal is None:
                return {"status": "error", "error": f"deal {deal_id} not found"}
            amount = f"{deal.amount:.2f} {deal.currency}" if deal.amount is not None else "—"
            lines = [
                headline,
                "",
                f"🆔 {deal.number}",
                f"🏢 {_name(session, deal.buyer_company_id)}"
                f" → {_name(session, deal.seller_company_id)}",
                f"💰 {amount}",
                f"📊 {deal.status}",
                *(extra or []),
            ]
            asyncio.run(bot.send_message(chat_id=chat_id, text="\n".join(lines)[:4096]))
    except Exception as exc:  # noqa: BLE001 — a bot/DB hiccup must not kill the worker
        logger.error("notify.deal_card.error", extra={"deal_id": deal_id, "error": str(exc)})
        return {"status": "error", "error": str(exc)}

    logger.info("notify.deal_card.sent", extra={"deal_id": deal_id, "chat_id": chat_id})
    return {"status": "ok", "error": None}


@celery_app.task(name="send_deal_opened_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_deal_opened_to_group(
    event_id: int | None = None,
    aggregate_id: str | None = None,
    payload: Any = None,
) -> dict[str, Any]:
    """DEAL_OPENED consumer — read-only staff awareness card (ru/uz/tr). Never raises."""
    return _deal_card(
        aggregate_id or (payload or {}).get("deal_id"),
        "🤝 Открыта сделка · Bitim ochildi · İşlem açıldı",
    )


@celery_app.task(name="send_deal_status_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_deal_status_to_group(
    event_id: int | None = None,
    aggregate_id: str | None = None,
    payload: Any = None,
) -> dict[str, Any]:
    """DEAL_STATUS_CHANGED consumer — cards ONLY for disputes.

    Every transition emits this event; the staff group only wants the ones that
    need a human, so anything but `disputed` is skipped rather than filtered at
    the dispatcher (which routes by type, not payload).
    """
    data = payload or {}
    if data.get("to") != "disputed":
        return {"status": "skipped", "error": None}
    reason = data.get("reason")
    extra = [f"⚠️ {reason}"] if reason else []
    return _deal_card(
        aggregate_id or data.get("deal_id"),
        "🚩 Спор по сделке · Bitim bo‘yicha nizo · İşlem anlaşmazlığı",
        extra,
    )


@celery_app.task(name="send_escrow_funded_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_escrow_funded_to_group(
    event_id: int | None = None,
    aggregate_id: str | None = None,
    payload: Any = None,
) -> dict[str, Any]:
    """ESCROW_FUNDED consumer — money ARRIVED, which is what operators act on.

    Only this one of the four escrow events carries a card: raising an invoice
    and paying out are routine, but funds landing is the moment the seller can
    be told to ship and the operator's reconciliation is on the clock.

    `aggregate_id` is the payment id, so the deal comes from the payload.
    Never raises (ru/uz/tr, fail-soft like the other cards).
    """
    data = payload or {}
    amount = f"{data.get('amount', '—')} {data.get('currency', '')}".strip()
    note = data.get("note")
    extra = [f"💵 {amount}"]
    if note:
        extra.append(f"📝 {note}")
    return _deal_card(
        data.get("deal_id"),
        "💰 Escrow пополнен · Escrow to‘ldirildi · Escrow'a para geldi",
        extra,
    )


@celery_app.task(name="send_lab_order_to_group", queue="notify")  # type: ignore[untyped-decorator]
def send_lab_order_to_group(
    event_id: int | None = None,
    aggregate_id: str | None = None,
    payload: Any = None,
) -> dict[str, Any]:
    """LAB_ORDER_SUBMITTED consumer — a customer has asked for an analysis.

    This card is the START of a manual process: nobody is watching the dashboard
    queue at 9pm, and the whole feature depends on someone picking the phone up
    and calling a laboratory. Only submission gets a card — the statuses after it
    are moved by the same operator who is already looking at the queue.

    Never raises (ru/uz/tr, fail-soft like the other cards).
    """
    data = payload or {}
    lab_order_id = aggregate_id or data.get("lab_order_id")
    if lab_order_id is None:
        return {"status": "skipped", "error": "no_lab_order_id"}

    chat_id = _verification_notify_chat_id()
    if chat_id is None:
        return {"status": "skipped", "error": "no_chat_id"}

    from sqlalchemy.orm import Session  # noqa: PLC0415
    from telegram.bot import bot  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.companies.models import Company  # noqa: PLC0415
    from app.models.lab import LabOrder  # noqa: PLC0415

    try:
        with Session(engine) as session:
            order = session.get(LabOrder, int(lab_order_id))
            if order is None:
                return {"status": "error", "error": f"lab order {lab_order_id} not found"}
            company = session.get(Company, order.company_id)
            customer = (
                (company.legal_name or company.short_name or company.tax_id)
                if company is not None
                else str(order.company_id)
            )
            subject = (
                f"оффер #{order.offer_id}"
                if order.offer_id is not None
                else f"сделка #{order.deal_id}"
            )
            lines = [
                "🧪 Новая лабораторная заявка"
                " · Yangi laboratoriya arizasi"
                " · Yeni laboratuvar talebi",
                "",
                f"🆔 {order.number}",
                f"🏢 {customer}",
                f"📦 {subject}",
            ]
            if order.sample_volume:
                lines.append(f"⚖️ {order.sample_volume}")
            if order.comment:
                lines.append(f"📝 {order.comment}")
            asyncio.run(bot.send_message(chat_id=chat_id, text="\n".join(lines)[:4096]))
    except Exception as exc:  # noqa: BLE001 — a bot/DB hiccup must not kill the worker
        logger.error(
            "notify.lab_order.error", extra={"lab_order_id": lab_order_id, "error": str(exc)}
        )
        return {"status": "error", "error": str(exc)}

    logger.info(
        "notify.lab_order.sent", extra={"lab_order_id": lab_order_id, "chat_id": chat_id}
    )
    return {"status": "ok", "error": None}


def _register_consumers() -> None:
    """Wire outbox events → team group cards (see events.CONSUMERS)."""
    from app.services import event_types  # noqa: PLC0415
    from app.tasks.events import CONSUMERS  # noqa: PLC0415

    if send_escrow_funded_to_group not in CONSUMERS.get(event_types.ESCROW_FUNDED, []):
        CONSUMERS[event_types.ESCROW_FUNDED].append(send_escrow_funded_to_group)

    if send_deal_opened_to_group not in CONSUMERS.get(event_types.DEAL_OPENED, []):
        CONSUMERS[event_types.DEAL_OPENED].append(send_deal_opened_to_group)
    if send_deal_status_to_group not in CONSUMERS.get(event_types.DEAL_STATUS_CHANGED, []):
        CONSUMERS[event_types.DEAL_STATUS_CHANGED].append(send_deal_status_to_group)

    if send_verification_case_to_group not in CONSUMERS.get(event_types.VERIFICATION_CASE_SUBMITTED, []):
        CONSUMERS[event_types.VERIFICATION_CASE_SUBMITTED].append(send_verification_case_to_group)
    if send_contract_activated_to_group not in CONSUMERS.get(event_types.CONTRACT_ACTIVATED, []):
        CONSUMERS[event_types.CONTRACT_ACTIVATED].append(send_contract_activated_to_group)

    if send_lab_order_to_group not in CONSUMERS.get(event_types.LAB_ORDER_SUBMITTED, []):
        CONSUMERS[event_types.LAB_ORDER_SUBMITTED].append(send_lab_order_to_group)


_register_consumers()
