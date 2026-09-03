"""Didox status polling (P7.a Stage 2 — W10). Beat, on the `verify` queue.

**There are no partner webhooks.** Didox publishes none, so the only way we learn
that a counterparty signed — or that the tax committee annulled a document — is to
ask. `GET /v2/documents` with `dateFromUpdated` is the incremental cursor.

Four properties, each copied from `reconcile_escrow_payments` for the same reasons
it has them:

* **Mode gate before any I/O.** On `didox_mode='stub'` this returns
  `{"status": "disabled"}` rather than quietly polling nothing — a stub standing
  in for an EDI operator is exactly the confusion the rail must not create.
* **It never raises.** A beat that raises just retries the same failure on the
  next tick; failures come back as `{"status": "error"}`.
* **The cursor is deliberately overlapped by a day.** `dateFromUpdated` has DAY
  granularity, so it cannot be an exactly-once cursor. Pages repeat, and
  `edi_service.apply_status` is forward-only precisely so a repeat is harmless.
* **Nothing bad auto-applies.** `3` (signed) fetches the archive and activates;
  `4` (rejected) and `50` (annulled by the tax committee) are recorded and
  alerted, and change no state of ours. `active` is terminal and a deal may
  already be riding on it — a silent move to some new terminal state would leave
  that deal without footing.

Companies with no cached `user-key` are skipped in silence: we cannot mint one for
them (it needs their own E-IMZO key, in their browser), and the synchronous path
already covers the common case — when a party signs in OUR cabinet we hold a fresh
key in that very request and activate immediately. This poller is the safety net
for the counterparty who signed in their own EDI cabinet, and for `4`/`50`.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

#: How far back to re-read. One day of overlap because `dateFromUpdated` is
#: day-granular: asking from "today" would miss anything Didox stamped earlier in
#: the same day we last ran.
_OVERLAP = datetime.timedelta(days=1)

#: Statuses that mean a human has to look, and that we never act on ourselves.
_ALERTING = (4, 50)


@celery_app.task(name="poll_didox_documents", queue="verify")  # type: ignore[untyped-decorator]
def poll_didox_documents(limit: int = 100) -> dict[str, Any]:
    """Ask Didox where each live document stands (beat — the `verify` queue).

    `verify` because this CALLS OUT: the queue exists so a slow or dead provider
    cannot starve ingest/parse/notify.
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.edi import onboarding  # noqa: PLC0415

    try:
        with Session(engine) as db:
            try:
                onboarding.assert_live()
            except onboarding.ChannelDisabled:
                return {"status": "disabled", "reason": "didox_mode is not 'live'"}
            report = _poll(db, limit=limit)
            db.commit()
    except Exception as exc:  # noqa: BLE001 — a beat that raises just retries the same failure
        logger.exception("edi_tasks.poll_failed")
        return {"status": "error", "error": str(exc)}

    alerts = report.get("alerts") or []
    if isinstance(alerts, list) and alerts:
        _alert_terminal(alerts)
    logger.info("edi_tasks.poll", extra={k: v for k, v in report.items() if k != "alerts"})
    return {"status": "ok", **report}


def _poll(db: Any, *, limit: int) -> dict[str, Any]:  # noqa: ANN401 — Session, imported lazily
    from app.core.time import utcnow  # noqa: PLC0415
    from app.domains.edi import service as edi_service  # noqa: PLC0415
    from app.domains.edi.models import DidoxCompany, DidoxDocument  # noqa: PLC0415
    from app.domains.edi.session import cached_user_key  # noqa: PLC0415
    from app.integrations.didox import ProviderUnavailable, get_didox_client  # noqa: PLC0415

    redis_client = _redis()
    client = get_didox_client()
    now = utcnow()

    #: Only documents that can still change. A deleted or already-signed document
    #: has nothing left to learn, and asking about it burns a page of the cursor.
    live = (
        db.query(DidoxDocument)
        .filter(
            DidoxDocument.didox_id.isnot(None),
            DidoxDocument.status.notin_([3, 4, 5, 50, 55]),
        )
        .order_by(DidoxDocument.id)
        .limit(limit)
        .all()
    )
    if not live:
        return {"checked": 0, "advanced": 0, "activated": 0, "skipped_no_key": 0, "alerts": []}

    by_company: dict[int, list[Any]] = {}
    for row in live:
        by_company.setdefault(row.owner_company_id, []).append(row)

    checked = advanced = activated = skipped = 0
    alerts: list[dict[str, Any]] = []

    for company_id, rows in by_company.items():
        record = db.get(DidoxCompany, company_id)
        tin = record.tin if record else None
        user_key = cached_user_key(redis_client, tin) if tin else None
        if not user_key:
            # Not an error: we cannot mint this key ourselves, and the user will
            # bring one the next time they act.
            skipped += len(rows)
            continue

        for row in rows:
            checked += 1
            try:
                view = client.get_document(row.didox_id, owner=1, user_key=user_key)
            except ProviderUnavailable as exc:
                logger.warning(
                    "edi_tasks.poll.unavailable",
                    extra={"doc_id": row.id, "error": str(exc)},
                )
                continue
            except Exception as exc:  # noqa: BLE001 — one bad row must not stop the sweep
                logger.warning("edi_tasks.poll.row_failed", extra={"doc_id": row.id, "error": str(exc)})
                row.last_error = str(exc)[:500]
                continue

            before = row.status
            became_active = edi_service.apply_status(
                db, row, view.status, user_key=user_key, client=client
            )
            if row.status != before:
                advanced += 1
            if became_active:
                activated += 1
            if row.status in _ALERTING and before not in _ALERTING:
                alerts.append(
                    {"doc_id": row.id, "didox_id": row.didox_id,
                     "number": row.number, "status": row.status}
                )

        if record is not None:
            # Overlapped on purpose — see `_OVERLAP`.
            record.last_polled_at = now - _OVERLAP
    db.flush()
    return {
        "checked": checked, "advanced": advanced, "activated": activated,
        "skipped_no_key": skipped, "alerts": alerts,
    }


def _redis() -> Any | None:  # noqa: ANN401 — redis.Redis, imported lazily
    """The poller runs in a worker, so it opens its own connection."""
    try:
        import redis  # noqa: PLC0415

        from app.core.config import settings  # noqa: PLC0415

        return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as exc:  # noqa: BLE001 — no cache means "skip", never "crash"
        logger.warning("edi_tasks.redis_unavailable", extra={"error": str(exc)})
        return None


def _alert_terminal(alerts: list[dict[str, Any]]) -> None:
    """Best-effort admin alert for `4` / `50` (never raises).

    These are LEGAL events for a person: a counterparty refused, or the tax
    committee annulled a document that may already have a deal riding on it.
    Mirrors `payments._alert_divergence`.
    """

    from app.services import settings_service  # noqa: PLC0415

    chat_id = settings_service.verification_chat_id()
    if chat_id is None:
        return
    try:
        import asyncio  # noqa: PLC0415

        from telegram.bot import bot  # noqa: PLC0415

        lines = "\n".join(
            f"• {a.get('number') or a.get('didox_id')} — статус {a.get('status')}"
            f"{' (аннулирован НК)' if a.get('status') == 50 else ' (отказ контрагента)'}"
            for a in alerts
        )
        text = (
            "⚠️ Didox: документ в терминальном состоянии "
            "(автоматический переход НЕ выполнен).\n" + lines
        )
        asyncio.run(bot.send_message(chat_id=chat_id, text=text[:4096]))
    except Exception as exc:  # noqa: BLE001
        logger.error("edi_tasks.poll_alert_failed", extra={"error": str(exc)})
