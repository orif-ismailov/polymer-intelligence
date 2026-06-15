"""
Placeholder task bodies for the five scheduled task names.

These ensure the Celery worker boots without "NotRegistered" errors before the
actual implementation plans land:
  - 02-04: uzex_fetch_offers, uzex_fetch_contracts, uzex_fetch_deals
  - 02-05: fetch_cbu_rates
  - 02-06: check_source_health

Each placeholder:
1. Is registered under the exact contract task name (the name that beat_schedule
   references and that later plans REPLACE — not the name of this module).
2. Logs a structured `not_yet_implemented` warning instead of raising so the
   worker does not crash-loop when beat fires the task prematurely.
3. Returns a dict carrying `status="not_yet_implemented"` so callers / tests
   can detect placeholder execution.

When 02-04/05/06 land they define `@celery_app.task(name="<same_name>")` which
OVERWRITES the placeholder registration — no cleanup of this file is needed;
the later definition simply wins.
"""

from __future__ import annotations

import logging
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="uzex_fetch_offers")  # type: ignore[untyped-decorator]
def placeholder_uzex_fetch_offers() -> dict[str, Any]:
    """Placeholder for UZEX offers fetcher (implemented in plan 02-04)."""
    logger.warning(
        "not_yet_implemented",
        extra={"task": "uzex_fetch_offers", "plan": "02-04"},
    )
    return {"status": "not_yet_implemented", "task": "uzex_fetch_offers"}


@celery_app.task(name="uzex_fetch_contracts")  # type: ignore[untyped-decorator]
def placeholder_uzex_fetch_contracts() -> dict[str, Any]:
    """Placeholder for UZEX contracts fetcher (implemented in plan 02-04)."""
    logger.warning(
        "not_yet_implemented",
        extra={"task": "uzex_fetch_contracts", "plan": "02-04"},
    )
    return {"status": "not_yet_implemented", "task": "uzex_fetch_contracts"}


@celery_app.task(name="uzex_fetch_deals")  # type: ignore[untyped-decorator]
def placeholder_uzex_fetch_deals() -> dict[str, Any]:
    """Placeholder for UZEX concluded deals fetcher (implemented in plan 02-04)."""
    logger.warning(
        "not_yet_implemented",
        extra={"task": "uzex_fetch_deals", "plan": "02-04"},
    )
    return {"status": "not_yet_implemented", "task": "uzex_fetch_deals"}


@celery_app.task(name="fetch_cbu_rates")  # type: ignore[untyped-decorator]
def placeholder_fetch_cbu_rates() -> dict[str, Any]:
    """Placeholder for CBU FX rates importer (implemented in plan 02-05)."""
    logger.warning(
        "not_yet_implemented",
        extra={"task": "fetch_cbu_rates", "plan": "02-05"},
    )
    return {"status": "not_yet_implemented", "task": "fetch_cbu_rates"}


@celery_app.task(name="check_source_health")  # type: ignore[untyped-decorator]
def placeholder_check_source_health() -> dict[str, Any]:
    """Placeholder for source health checker (implemented in plan 02-06)."""
    logger.warning(
        "not_yet_implemented",
        extra={"task": "check_source_health", "plan": "02-06"},
    )
    return {"status": "not_yet_implemented", "task": "check_source_health"}
