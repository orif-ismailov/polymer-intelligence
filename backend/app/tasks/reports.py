"""
News-engine Celery tasks (Phase 3).

generate_daily_report builds today's market report as a draft (human-in-the-loop:
staff approve → publish on the dashboard). Scheduled by beat; see app/tasks/schedule.py.
"""

from __future__ import annotations

import logging

from app.core.db import SessionLocal
from app.services import report_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_daily_report")
def generate_daily_report() -> int | None:
    """Generate today's report (draft). Returns the new report id, or None on failure."""
    with SessionLocal() as db:
        try:
            report = report_service.generate_report(db)
            db.commit()
            logger.info("generate_daily_report.done", extra={"report_id": report.id})
            return report.id
        except Exception:
            logger.exception("generate_daily_report.failed")
            db.rollback()
            return None


@celery_app.task(name="publish_report_to_channel", queue="notify")
def publish_report_to_channel(report_id: int) -> dict[str, object]:
    """Post a published report's digest to the Telegram news channel (best-effort).

    No-op (logged) when NEWS_CHANNEL_ID is empty so dev/test never call Telegram.
    Never raises — returns a status dict so the worker stays alive (T-03-13 pattern).
    A compact (≤1500-char, brand-footed) Telegram digest is rendered from the report's
    data snapshot; if the snapshot is missing (legacy reports) it falls back to
    content_md. Sent as Telegram Markdown; a single URL button opens the Mini App.
    """
    import asyncio  # noqa: PLC0415

    from telegram.bot import bot  # noqa: PLC0415

    from app.core.config import settings as _settings  # noqa: PLC0415

    if not _settings.NEWS_CHANNEL_ID:
        logger.info("publish_report_to_channel.skipped_no_channel", extra={"report_id": report_id})
        return {"status": "skipped", "error": None}

    with SessionLocal() as db:
        report = report_service.get_report(db, report_id)
        if report is None:
            return {"status": "error", "error": f"Report {report_id} not found"}
        snapshot = report.data_snapshot
        if isinstance(snapshot, dict) and snapshot:
            content = report_service.render_telegram_digest(snapshot)
        else:  # legacy report with no snapshot — degrade to the archival body
            content = report.content_md

    try:
        reply_markup = None
        if _settings.PUBLIC_WEBAPP_URL:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: PLC0415

            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Открыть приложение", url=f"{_settings.PUBLIC_WEBAPP_URL.rstrip('/')}/")]
                ]
            )
        asyncio.run(
            bot.send_message(
                chat_id=_settings.NEWS_CHANNEL_ID,
                text=content,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("publish_report_to_channel.error", extra={"report_id": report_id, "error": str(exc)})
        return {"status": "error", "error": str(exc)}

    logger.info("publish_report_to_channel.done", extra={"report_id": report_id})
    return {"status": "ok", "error": None}
