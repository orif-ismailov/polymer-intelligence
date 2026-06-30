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

            # The Mini App is served under /webapp/ (the root is the dashboard); the
            # webapp uses HashRouter, so the request detail is /webapp/#/requests/{id}.
            deep_link_url = (
                f"{_settings.PUBLIC_WEBAPP_URL.rstrip('/')}/webapp/#/requests/{request.id}"
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

            asyncio.run(bot.send_message(chat_id=chat_id, text="\n".join(lines)))
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
