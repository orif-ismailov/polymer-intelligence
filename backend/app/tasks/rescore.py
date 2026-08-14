"""
Celery task: rescore_signals_for_prompt_version

Triggered when SCORING_PROMPT_VERSION is bumped in parsing/lead_scoring.py
to backfill all affected signals with the new lead score algorithm.

Trigger:
    This task is manually/admin-initiated — NOT on the periodic beat schedule.
    Invoke it when deploying a new scoring prompt version:

        from app.tasks.rescore import rescore_signals_for_prompt_version
        rescore_signals_for_prompt_version.apply_async(
            kwargs={"new_version": "lead_v2"},
            queue="parse",
        )

    Or via Celery CLI:
        celery -A app.tasks.celery_app call rescore_signals_for_prompt_version \\
            --kwargs '{"new_version": "lead_v2"}'

Design:
    - Runs bounded batches inside the service (batch_size=500 per flush).
    - Routes to the "parse" queue (same as LLM extraction tasks).
    - WR-09: single commit semantics. The service flushes per batch but the task
      commits ONCE after the whole run completes successfully. A mid-run failure
      therefore rolls back ALL batches (no partial persistence), and the
      reported rescored_count on the success path always matches persisted work.
    - Idempotent: signals already at the new version are skipped.
    - Returns the total count of re-scored signals.

Security:
    T-05-24: Each re-scored signal is stamped with new scoring_prompt_version +
             scored_at (rescore_on_prompt_version_change invariant).
"""

from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app
from parsing.lead_scoring import SCORING_PROMPT_VERSION

logger = logging.getLogger(__name__)


@celery_app.task(
    name="rescore_signals_for_prompt_version",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def rescore_signals_for_prompt_version(
    self,  # noqa: ANN001 — bound Celery task
    new_version: str = SCORING_PROMPT_VERSION,
    batch_size: int = 500,
) -> dict[str, object]:
    """Backfill lead scores for signals with a stale scoring_prompt_version.

    Args:
        new_version: Target scoring_prompt_version (default: current constant).
        batch_size: Rows per DB batch (default: 500).

    Returns:
        Dict with keys:
          - new_version (str): The version stamped on re-scored signals.
          - rescored_count (int): Total signals re-scored.
          - status (str): "ok" or "error".
    """
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.domains.signals.lead_score_recompute import (  # noqa: PLC0415
        rescore_on_prompt_version_change,
    )

    logger.info(
        "rescore_task.start",
        extra={"new_version": new_version, "batch_size": batch_size},
    )

    try:
        rescored_count = 0
        # Process in bounded chunks so the task is cancellable between batches.
        # rescore_on_prompt_version_change internally batches and flushes;
        # we commit after the full run (acceptable for a background backfill).
        with SessionLocal() as session:
            rescored_count = rescore_on_prompt_version_change(
                session,
                new_version=new_version,
                batch_size=batch_size,
            )
            session.commit()

        logger.info(
            "rescore_task.complete",
            extra={"new_version": new_version, "rescored_count": rescored_count},
        )
        return {
            "new_version": new_version,
            "rescored_count": rescored_count,
            "status": "ok",
        }

    except Exception as exc:
        logger.error(
            "rescore_task.error",
            extra={"new_version": new_version, "error": str(exc)},
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "new_version": new_version,
                "rescored_count": 0,
                "status": "error",
                "error": str(exc),
            }
