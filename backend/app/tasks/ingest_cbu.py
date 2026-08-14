"""
CBU FX rates fetch task.

Registers the real `fetch_cbu_rates` Celery task that supersedes the
placeholder in tasks/placeholders.py (same task name; last registration wins
during autodiscovery — Celery resolves by name, not by module).

Beat schedule (from 02-01/schedule.py):
    fetch_cbu_rates — crontab(minute=0, hour=7)  → daily at 07:00 Tashkent

Workflow:
1. Load the cbu_rates source row from the DB (adapter="cbu_rates", is_enabled=True).
2. Fetch and parse the CBU JSON via the CbuRatesAdapter.
3. Upsert all parsed rates into fx_rates (idempotent ON CONFLICT).
4. Update source.last_fetch_at and source.last_success_at.

Security:
  T-02-15: Decimal parsing handled by CbuRatesAdapter._parse_cbu_json.
  T-02-16: All DB writes use bound parameters (via fx_service).
  T-02-17: Failures caught, journaled, and do NOT crash sibling tasks.
  T-02-18: last_fetch_at / last_success_at provide traceability at source level.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="fetch_cbu_rates")  # type: ignore[untyped-decorator]
def fetch_cbu_rates() -> dict[str, Any]:
    """Fetch the daily CBU exchange rates and upsert them into fx_rates.

    This task supersedes the placeholder in placeholders.py. It:
    - Loads the cbu_rates Source from the DB (adapter='cbu_rates', is_enabled=True)
    - Fetches the CBU JSON via CbuRatesAdapter
    - Upserts all rate rows via fx_service.upsert_fx_rates (idempotent)
    - Updates source.last_fetch_at and source.last_success_at on success

    Returns:
        A dict with keys: status, upserted (int), error (str | None)
    """
    import asyncio  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.domains.pricing.fx import upsert_fx_rates  # noqa: PLC0415
    from app.ingest.cbu_rates.adapter import CbuRatesAdapter  # noqa: PLC0415

    logger.info("fetch_cbu_rates.start")
    now = datetime.datetime.now(tz=datetime.UTC)

    adapter = CbuRatesAdapter()

    with Session(engine) as session:
        # Load the cbu_rates source (there may be none if not yet configured)
        source_row = session.execute(
            sa.text(
                """
                SELECT id FROM sources
                WHERE adapter = 'cbu_rates' AND is_enabled = true
                LIMIT 1
                """
            )
        ).fetchone()

        source_id = source_row[0] if source_row else None

        # If no source row exists, still fetch and upsert rates globally
        # (the source row is used for tracking, not for the fetch itself)
        if source_id is not None:
            # Mark fetch attempt
            session.execute(
                sa.text(
                    "UPDATE sources SET last_fetch_at = :now WHERE id = :id"
                ),
                {"now": now, "id": source_id},
            )
            session.commit()

    # Fetch and parse the CBU JSON.
    # WR-07: use the adapter's fetch() method (which reads source.config.endpoint_url)
    # rather than a private helper that always fetches from the hardcoded default URL.
    # This makes the endpoint_url override in CbuRatesConfig actually functional in
    # the scheduled task path (previously it was honoured only in test() and the
    # protocol-compliance fetch() path, but the Celery task bypassed both).
    try:
        with Session(engine) as session:
            if source_id is not None:
                from app.domains.signals.source_models import Source  # noqa: PLC0415

                source_obj = session.get(Source, source_id)
                if source_obj is not None:
                    rate_row_drafts = asyncio.run(adapter.fetch(source_obj))
                else:
                    rate_row_drafts = asyncio.run(_fetch_default_drafts(adapter))
            else:
                rate_row_drafts = asyncio.run(_fetch_default_drafts(adapter))
        # Convert RawItemDraft payloads back to CbuRateRow objects for upsert
        import datetime as _dt  # noqa: PLC0415
        import decimal as _dec  # noqa: PLC0415

        from app.ingest.cbu_rates.adapter import CbuRateRow  # noqa: PLC0415

        rate_rows = []
        for draft in rate_row_drafts:
            p = draft.payload or {}
            try:
                rate_rows.append(
                    CbuRateRow(
                        rate_date=_dt.date.fromisoformat(str(p["rate_date"])),
                        ccy=str(p["ccy"]),
                        rate=_dec.Decimal(str(p["rate"])),
                    )
                )
            except (KeyError, ValueError, _dec.InvalidOperation):
                continue
    except Exception as exc:
        logger.error("fetch_cbu_rates.fetch_error", extra={"error": str(exc)})
        return {"status": "error", "upserted": 0, "error": str(exc)}

    # Upsert into fx_rates
    with Session(engine) as session:
        try:
            upserted = upsert_fx_rates(session, rate_rows)
            session.commit()
        except Exception as exc:
            logger.error("fetch_cbu_rates.upsert_error", extra={"error": str(exc)})
            session.rollback()
            return {"status": "error", "upserted": 0, "error": str(exc)}

        # Update success timestamps
        if source_id is not None:
            session.execute(
                sa.text(
                    """
                    UPDATE sources
                    SET last_success_at = :now, consecutive_failures = 0
                    WHERE id = :id
                    """
                ),
                {"now": now, "id": source_id},
            )
            session.commit()

    logger.info("fetch_cbu_rates.done", extra={"upserted": upserted})
    return {"status": "ok", "upserted": upserted, "error": None}


async def _fetch_default_drafts(adapter: object) -> list[object]:
    """Async helper: fetch CBU rates from the default URL when no source row exists.

    WR-07: replaces _fetch_cbu_body (which always used the hardcoded URL and bypassed
    source.config). When a source row IS available, adapter.fetch(source) is called
    instead so endpoint_url from source.config is honoured.
    """
    from app.ingest.cbu_rates.adapter import _CBU_DEFAULT_URL  # noqa: PLC0415

    class _FakeSource:
        """Minimal Source duck-type for the adapter protocol when no DB row exists."""
        config: dict = {"endpoint_url": _CBU_DEFAULT_URL}

    return await adapter.fetch(_FakeSource())  # type: ignore[arg-type, union-attr]
