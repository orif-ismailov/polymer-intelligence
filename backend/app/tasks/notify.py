"""
Notify Celery tasks module.

Tasks:
  check_source_health — scans all enabled sources for 3-strike failures (≤30 min SLA).
  send_status_change_notification — pushes D-10 localized status update to client via bot.

check_source_health:
  Supersedes the placeholder in tasks/placeholders.py (same task name; last
  registration wins during autodiscovery — Celery resolves by name, not by module).
  Beat schedule: crontab(minute="*/5") → every 5 minutes.

  Security:
    T-02-20: alert deduplication via source_health_service.raise_source_failure_alert
             (ON CONFLICT DO NOTHING on dedupe_key) — no alert storm.
    T-02-22: defense in depth for the ≤30 min guarantee (independent scan).

send_status_change_notification:
  Sends a localized D-10 status push to the client via the aiogram Bot.
  Queue: notify (≤30 s delivery SLA for REQ-nfr-performance).

  Security:
    T-03-12: deep-link button targets recipient's own request — no cross-client leak.
    T-03-13: task never raises — always returns error dict so the worker stays alive.
"""

from __future__ import annotations

import asyncio
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

_LANG_LABEL_MAP: dict[str, dict[str, str]] = {
    "ru": _RU_STATUS_LABELS,
    "uz": _UZ_STATUS_LABELS,
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

    from app.core.config import settings as _settings  # noqa: PLC0415
    from app.core.db import engine  # noqa: PLC0415
    from app.models.requests import Request  # noqa: PLC0415
    from app.services.request_service import client_facing_status  # noqa: PLC0415
    from telegram.bot import bot, load_template, web_app_keyboard  # noqa: PLC0415

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
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo  # noqa: PLC0415

            deep_link_url = f"{_settings.PUBLIC_WEBAPP_URL}/#/requests/{request.id}"
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

            session.commit()

    except Exception as exc:
        logger.error(
            "notify.status_change.error",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return {"status": "error", "error": str(exc)}

    logger.info("notify.status_change.done", extra={"request_id": request_id})
    return {"status": "ok", "error": None}
