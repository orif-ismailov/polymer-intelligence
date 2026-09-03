"""
Retention for the integration gateway call log.

`app/models/integration.py` has said "Prunable (90-day retention, §13)" since R3
and nothing ever pruned it. That was harmless while the table held a few hundred
E-IMZO calls. It stops being harmless now: `/admin/analytics` exists to measure a
package of a MILLION Didox requests a month, and a table growing by a million
rows a month forever is the thing that page is watching being fed.

Ninety days is the figure the model already committed to, and it is also what the
analytics page needs — three months is enough for month-over-month, and the row
holds no evidence, only call metadata (evidence lives in `signature_evidence` and
`registry_snapshots`, which are immutable and are NOT touched here).

The consequence, stated rather than discovered: **months older than three do not
exist afterwards.** If a year of history is ever wanted, it wants a rollup table
written before this deletes the rows, not a longer retention on the raw log.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, cast

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

#: The retention `app/models/integration.py` documents. One place, so the model's
#: docstring and the task that enforces it cannot drift apart again.
RETENTION_DAYS = 90


@celery_app.task(name="prune_integration_call_log")  # type: ignore[untyped-decorator]
def prune_integration_call_log() -> dict[str, Any]:
    """Delete gateway call-log rows older than the retention window."""
    from sqlalchemy import delete  # noqa: PLC0415
    from sqlalchemy.engine import CursorResult  # noqa: PLC0415
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.core.time import utcnow  # noqa: PLC0415
    from app.models.integration import IntegrationCallLog  # noqa: PLC0415

    cutoff = utcnow() - datetime.timedelta(days=RETENTION_DAYS)
    with Session(engine) as db:
        # `Session.execute` is typed `Result`, which has no `rowcount`; a DELETE
        # always returns the `CursorResult` that does.
        result = cast(
            "CursorResult[Any]",
            db.execute(delete(IntegrationCallLog).where(IntegrationCallLog.created_at < cutoff)),
        )
        deleted = result.rowcount
        db.commit()

    logger.info("retention.integration_call_log", extra={"deleted": deleted})
    return {"status": "ok", "deleted": deleted}
