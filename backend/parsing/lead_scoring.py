"""
Phase 5 lead scoring pass.

Computes a 0-1 lead quality score and a HOT/MEDIUM/LOW classification for a
validated ExtractionResult. The score is deterministic and rules-based (CI-testable
without a live LLM call), per AI-SPEC §4b.5:
  "route scoring through a classification prompt on the same Haiku model rather
   than upgrading to Sonnet — but Phase-5 default is a deterministic rules score
   so it is CI-testable without a live call"

Scoring factors (additive, capped at 1.0):
  - Signal kind weight: deal/buy_request/sell_offer (actionable) score higher
    than price_quote/news (informational)
  - Volume presence + magnitude: large confirmed volume is a strong lead signal
  - Counterparty presence: named counterparty increases actionability
  - Urgency cue: HIGH urgency adds a significant boost
  - Confidence: extraction confidence propagates into the lead score

Classification thresholds:
  HOT   ≥ 0.70 — High-priority, assign to trader immediately
  MEDIUM ≥ 0.40 — Worth reviewing, assign to analyst
  LOW   < 0.40 — Informational, enters feed without priority flag

SCORING_PROMPT_VERSION versioning:
  When the scoring logic changes (new factors, threshold adjustments), bump
  SCORING_PROMPT_VERSION. The version is stamped into signals.ai:
    {lead_score, classification, model, prompt_version: SCORING_PROMPT_VERSION, scored_at}
  A version bump triggers the 05-05 Celery backfill that re-scores affected signals
  (REQ-lead-scoring: "recomputed on prompt-version change"). The gate harness
  (05-05) is re-run before promoting the new scoring version to production.

Usage:
    from parsing.lead_scoring import compute_lead_score, SCORING_PROMPT_VERSION

    score, classification = compute_lead_score(result)
    signals_ai_update = {
        "lead_score": score,
        "classification": classification,
        "prompt_version": SCORING_PROMPT_VERSION,
        "scored_at": datetime.now(tz=timezone.utc).isoformat(),
    }
"""

from __future__ import annotations

from parsing.schemas import ExtractionResult, SignalKind, UrgencyLevel

# ---------------------------------------------------------------------------
# Version pin (bump to trigger backfill re-scoring on all affected signals)
# ---------------------------------------------------------------------------

SCORING_PROMPT_VERSION: str = "lead_v1"
"""
Scoring algorithm version. Stored in signals.ai for audit + recompute tracking.

Rules (lead_v1):
  - kind weight: deal=0.35, sell_offer=0.30, buy_request=0.28, price_quote=0.10, news=0.05
  - volume factor: >100MT → +0.20, >10MT → +0.15, >0MT → +0.10
  - urgency factor: HIGH → +0.20, MEDIUM → +0.05, LOW → 0
  - counterparty factor: +0.10 if present
  - confidence factor: +0.05 if confidence ≥ 0.8
  Total is capped at 1.0.

Bump this string (e.g. "lead_v2") when any factor or threshold changes.
The 05-05 backfill will re-score all affected signals.
"""

# ---------------------------------------------------------------------------
# Classification thresholds (AI-SPEC §4b.5 + plan acceptance criteria)
# ---------------------------------------------------------------------------

_HOT_THRESHOLD: float = 0.70
"""Scores ≥ HOT_THRESHOLD → "HOT" — assign to trader immediately."""

_MEDIUM_THRESHOLD: float = 0.40
"""Scores ≥ MEDIUM_THRESHOLD and < HOT_THRESHOLD → "MEDIUM" — analyst review."""
# Below MEDIUM_THRESHOLD → "LOW" — informational only.

# ---------------------------------------------------------------------------
# Scoring factor weights (lead_v1)
# ---------------------------------------------------------------------------

_KIND_WEIGHTS: dict[SignalKind | None, float] = {
    SignalKind.DEAL:        0.35,   # completed deal — high actionability
    SignalKind.SELL_OFFER:  0.30,   # live offer — actionable
    SignalKind.BUY_REQUEST: 0.28,   # live buy — actionable (buy side)
    SignalKind.PRICE_QUOTE: 0.10,   # price information only
    SignalKind.NEWS:        0.05,   # market news — minimal lead value
    None:                   0.05,   # unknown kind — minimal
}

_URGENCY_WEIGHTS: dict[UrgencyLevel | None, float] = {
    UrgencyLevel.HIGH:   0.20,
    UrgencyLevel.MEDIUM: 0.05,
    UrgencyLevel.LOW:    0.00,
    None:                0.00,
}


def _volume_factor(result: ExtractionResult) -> float:
    """Return the volume contribution to the lead score."""
    if result.volume is None:
        return 0.0
    vol = float(result.volume)
    if vol > 100:
        return 0.20    # large lot — high priority
    if vol > 10:
        return 0.15    # medium lot
    if vol > 0:
        return 0.10    # small but confirmed volume
    return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify(score: float) -> str:
    """Map a 0-1 score to a HOT/MEDIUM/LOW classification string.

    Args:
        score: Lead quality score in [0.0, 1.0].

    Returns:
        str: "HOT" if score ≥ 0.70; "MEDIUM" if score ≥ 0.40; "LOW" otherwise.
    """
    if score >= _HOT_THRESHOLD:
        return "HOT"
    if score >= _MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def compute_lead_score(result: ExtractionResult) -> tuple[float, str]:
    """Compute a 0-1 lead quality score and HOT/MEDIUM/LOW classification.

    Scoring is deterministic (rules-based, no LLM call) and versioned under
    SCORING_PROMPT_VERSION. Each factor is additive; the total is capped at 1.0.

    Args:
        result: A validated ExtractionResult from the LLM extractor or rule-based
                fallback. Should have is_relevant=True (irrelevant messages are
                typically not scored, but the function handles them safely).

    Returns:
        tuple[float, str]: (score, classification)
            - score: float in [0.0, 1.0]
            - classification: "HOT", "MEDIUM", or "LOW"

    Note:
        The caller stamps {lead_score, classification, prompt_version: SCORING_PROMPT_VERSION,
        scored_at} into signals.ai. Bumping SCORING_PROMPT_VERSION triggers the 05-05
        backfill re-scoring affected signals (REQ-lead-scoring).
    """
    if not result.is_relevant:
        # Irrelevant messages have no lead value
        return 0.0, "LOW"

    # 1. Kind weight (base score)
    kind_weight = _KIND_WEIGHTS.get(result.kind, 0.05)

    # 2. Volume factor
    vol_factor = _volume_factor(result)

    # 3. Urgency factor
    urgency_weight = _URGENCY_WEIGHTS.get(result.urgency, 0.0)

    # 4. Counterparty presence factor
    counterparty_factor = 0.10 if result.counterparty_text else 0.0

    # 5. Confidence propagation (high-confidence extractions are more reliable leads)
    confidence_factor = 0.05 if result.confidence >= 0.8 else 0.0

    raw_score = (
        kind_weight
        + vol_factor
        + urgency_weight
        + counterparty_factor
        + confidence_factor
    )

    # Cap at 1.0 (all factors are additive and can sum beyond 1)
    score = min(raw_score, 1.0)

    classification = classify(score)
    return score, classification
