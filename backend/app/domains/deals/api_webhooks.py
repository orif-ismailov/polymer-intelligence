"""Escrow provider callback inbox (R6 / P7.b — T2.1). Under /api/v1/webhooks.

    POST /api/v1/webhooks/escrow/{provider}

The bank's side of the live escrow rail. Didox has no partner webhooks and the
bank's notification format is unknown, so this endpoint is deliberately dumb: it
authenticates, stores the bytes, and answers 200. Understanding the callback is
the task's job (`app.tasks.payments.apply_escrow_provider_event`).

That split is the whole design, and the order matters:

  1. **Authenticate** on a shared secret in `X-Escrow-Token`, constant-time
     (`hmac.compare_digest`, same shape as `telegram_webhook.py`). No configured
     secret → **404**, not 401: a deployment that does not use escrow should not
     confirm to a scanner that the rail exists.
  2. **Record**, then commit. The idempotency key comes from
     `events.extract_external_id`, which works on a payload we have not parsed —
     so a retry of a callback we cannot even read still collides on
     `UNIQUE (provider, external_id)` instead of piling up duplicates.
  3. **Answer 200**, then enqueue. A bank that receives 500 retries; a bank that
     receives 200 does not. So the response promises exactly one thing — this
     callback is durable — and nothing that can fail on a malformed payload is
     allowed to happen before it. A callback we could not read is still evidence.
  4. **Enqueue fail-soft.** A dropped `apply_async` costs latency, not data: the
     `sweep_provider_events` beat picks up anything still unprocessed. That is
     the reason the write and the dispatch are separate steps at all.

Not in the OpenAPI schema (`include_in_schema=False`) — an external contour is
not part of our published API surface.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
from typing import Any

from anyio import to_thread
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.domains.deals import escrow as escrow_service
from app.integrations.escrow import events as escrow_events

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

#: A callback carries a status and a reference, not a document. Anything larger
#: is either a mistake or an attempt to use the inbox as storage.
MAX_BODY_BYTES = 64 * 1024

#: `provider` lands in a column, so it is validated as a slug rather than taken
#: as free text from the network. An UNMAPPED provider is still accepted — the
#: evidence is worth keeping, and `apply_provider_event` holds it for an operator
#: with `unknown_provider`.
_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@router.post("/escrow/{provider}", include_in_schema=False)
async def escrow_callback(
    provider: str,
    request: Request,
    x_escrow_token: str | None = Header(default=None, alias="X-Escrow-Token"),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Store one provider callback and schedule its interpretation."""
    secret = settings.ESCROW_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not x_escrow_token or not hmac.compare_digest(x_escrow_token, secret):
        logger.warning("escrow.webhook.unauthorized", extra={"provider": provider})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    if not _PROVIDER_RE.match(provider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="body_too_large"
        )

    parsed = _parse(raw)
    payload: dict[str, Any] = (
        parsed if isinstance(parsed, dict) else {"_raw": raw.decode("utf-8", "replace")}
    )
    external_id = escrow_events.extract_external_id(provider, parsed, raw)

    # This handler has to be a coroutine — `await request.body()` is the only way
    # to read a body of unknown content type. But everything after it is blocking
    # (a DB insert + commit, then a Redis dispatch), and on the event loop that
    # stalls every other request in the process, SSE streams included. So the
    # blocking half goes to a worker thread. The ORDER the docstring promises is
    # unchanged: record, commit, then enqueue — the two calls stay separate so a
    # failed dispatch still costs latency rather than evidence.
    event_id = await to_thread.run_sync(_record, db, provider, external_id, payload)
    logger.info(
        "escrow.webhook.recorded",
        extra={"provider": provider, "external_id": external_id, "event_id": event_id},
    )

    await to_thread.run_sync(_schedule, event_id)
    return {"ok": True}


def _record(db: Session, provider: str, external_id: str, payload: dict[str, object]) -> int:
    """Persist the callback and commit. Returns the row id."""
    event = escrow_service.record_provider_event(db, provider, external_id, payload)
    db.commit()
    event_id: int = event.id
    return event_id


def _parse(raw: bytes) -> object | None:
    """Best-effort JSON. `None` when the body is not JSON at all."""
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None


def _schedule(event_id: int) -> None:
    """Enqueue the applier; a broker outage leaves the row for the sweeper."""
    try:
        from app.tasks.payments import apply_escrow_provider_event  # noqa: PLC0415

        apply_escrow_provider_event.apply_async(args=[event_id], retry=False)
    except Exception as exc:  # noqa: BLE001 — the callback is already durable
        logger.warning(
            "escrow.webhook.dispatch_failed",
            extra={"event_id": event_id, "error": str(exc)},
        )
