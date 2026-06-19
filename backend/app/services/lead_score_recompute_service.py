"""
Lead-score recompute-on-prompt-version-change service.

Implements the REQ-lead-scoring "recomputed on prompt-version change" path
(AI-SPEC §7 / 05-05 plan).

Background:
    signals.ai is the ONLY mutable AI output on a Signal row.  It stores:
        {lead_score, classification, model, prompt_version, scored_at,
         scoring_prompt_version, needs_review}
    All other Signal fields (kind, product, grade_text, volume, price, ...)
    are immutable after creation.

    When the scoring logic changes (SCORING_PROMPT_VERSION is bumped in
    parsing/lead_scoring.py), every signal whose ai->'scoring_prompt_version'
    differs from the new version must be re-scored and the ai JSONB overwritten.

    Re-scoring is safe because:
    - The ExtractionResult fields on the Signal row are immutable.
    - compute_lead_score is deterministic (rules-based, no LLM call).
    - The new scoring_prompt_version is stamped so the re-scored signals are
      attributable to the new algorithm (T-05-24 mitigated).

Usage:
    from app.services.lead_score_recompute_service import rescore_on_prompt_version_change

    with SessionLocal() as session:
        count = rescore_on_prompt_version_change(session, new_version="lead_v2")
        session.commit()

Service-never-commits axiom:
    This service calls session.flush() but NEVER session.commit().
    The caller (Celery task or admin script) is responsible for committing.

Security:
    T-05-24: Re-scored signal carries new scoring_prompt_version + scored_at so
             every row's lead score is always attributable to a known prompt version.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.signals import Signal
from parsing.lead_scoring import SCORING_PROMPT_VERSION, compute_lead_score
from parsing.schemas import (
    ExtractionResult,
    FieldConfidence,
    SignalKind,
    UrgencyLevel,
)

logger = logging.getLogger(__name__)


def _build_extraction_result_from_signal(signal: Signal) -> ExtractionResult:
    """Reconstruct a minimal ExtractionResult from immutable Signal fields.

    Only fields needed for compute_lead_score are populated:
    - is_relevant (always True for scored signals)
    - kind, volume, urgency, counterparty_text, confidence

    Args:
        signal: Signal ORM row.

    Returns:
        ExtractionResult compatible with compute_lead_score.
    """
    # Map Signal.kind (DB enum) back to parsing.schemas.SignalKind
    kind: SignalKind | None = None
    if signal.kind is not None:
        try:
            kind = SignalKind(signal.kind.value if hasattr(signal.kind, "value") else str(signal.kind))
        except ValueError:
            kind = None

    # Map Signal.urgency (DB enum) back to UrgencyLevel
    urgency: UrgencyLevel | None = None
    if signal.urgency is not None:
        try:
            urgency = UrgencyLevel(
                signal.urgency.value if hasattr(signal.urgency, "value") else str(signal.urgency)
            )
        except ValueError:
            urgency = None

    # Extract confidence from ai JSONB (default 0.8 for legacy rows without it)
    ai: dict[str, Any] = signal.ai or {}
    confidence: float = float(ai.get("confidence", 0.8))
    confidence = max(0.0, min(1.0, confidence))

    return ExtractionResult(
        is_relevant=True,
        kind=kind,
        product=signal.grade_text[:32] if signal.grade_text else None,
        grade_text=signal.grade_text[:128] if signal.grade_text else None,
        volume=signal.volume,
        volume_unit=signal.volume_unit or "MT",
        price=signal.price,
        currency=signal.currency,
        region=signal.region,
        counterparty_text=signal.counterparty_text,
        urgency=urgency,
        lead_score=None,  # will be recomputed
        confidence=confidence,
        field_confidence=FieldConfidence(),
    )


def rescore_on_prompt_version_change(
    session: Session,
    new_version: str = SCORING_PROMPT_VERSION,
    *,
    batch_size: int = 500,
) -> int:
    """Recompute lead scores for signals whose scoring_prompt_version differs from new_version.

    Selects signals where ai->>'scoring_prompt_version' != new_version (stale)
    AND the signal has an extraction result (ai is not empty), recomputes
    (score, classification) via compute_lead_score, and OVERWRITES signals.ai
    in place with the new lead_score / classification / scoring_prompt_version /
    scored_at.

    Immutable fields (kind, product, grade_text, volume, price, currency,
    counterparty_text, urgency) are read from the Signal row and fed to
    compute_lead_score without modification.

    Args:
        session: Active SQLAlchemy session.  Caller commits; this function flushes.
        new_version: The new scoring_prompt_version to stamp (default: current constant).
        batch_size: Max rows per SELECT batch (prevents unbounded memory use).

    Returns:
        int: Count of signals re-scored.

    Security:
        T-05-24: Each re-scored signal is stamped with new scoring_prompt_version +
                 scored_at so it is always attributable to a known algorithm version.
    """
    now_iso = datetime.datetime.now(tz=datetime.UTC).isoformat()
    rescored_count = 0
    offset = 0

    while True:
        # Select a batch of signals with stale scoring_prompt_version
        # ai->>'scoring_prompt_version' returns NULL if the key is absent — those are also stale
        stale_signals = (
            session.query(Signal)
            .filter(
                sa.or_(
                    Signal.ai["scoring_prompt_version"].as_string() != new_version,
                    Signal.ai["scoring_prompt_version"].as_string().is_(None),
                )
            )
            .filter(Signal.ai != sa.cast("{}", sa.dialects.postgresql.JSONB if hasattr(sa, "dialects") else sa.JSON))
            .order_by(Signal.id)
            .offset(offset)
            .limit(batch_size)
            .all()
        )

        if not stale_signals:
            break

        for signal in stale_signals:
            # Skip signals with empty or null ai (no extraction yet)
            if not signal.ai:
                continue

            try:
                result = _build_extraction_result_from_signal(signal)
                score, classification = compute_lead_score(result)
            except Exception as exc:
                logger.error(
                    "lead_score_recompute.score_failed",
                    extra={"signal_id": signal.id, "error": str(exc)},
                )
                continue

            # Overwrite signals.ai preserving immutable fields (model, prompt_version, needs_review)
            existing_ai = dict(signal.ai or {})
            existing_ai.update(
                {
                    "lead_score": score,
                    "classification": classification,
                    "scoring_prompt_version": new_version,
                    "scored_at": now_iso,
                }
            )
            signal.ai = existing_ai

            rescored_count += 1

        session.flush()
        offset += batch_size

        logger.info(
            "lead_score_recompute.batch_done",
            extra={
                "offset": offset,
                "batch_size": len(stale_signals),
                "rescored_total": rescored_count,
            },
        )

        if len(stale_signals) < batch_size:
            break

    logger.info(
        "lead_score_recompute.complete",
        extra={"new_version": new_version, "rescored_count": rescored_count},
    )
    return rescored_count
