"""
AI substance suggestion (P5 W4 — T4.1, FR-C3).

Reads a seller's free-text offer description and proposes ONE candidate
substance. The proposal is journalled in `substance_suggestions` and returned —
it is never written onto the offer. The seller confirms or rejects it, and that
decision is journalled too, because "the AI put a precursor on my listing" must
never be a true sentence.

Design mirrors `request_analysis_service`:
  - instructor + Anthropic, Mode.TOOLS, temperature 0, prompt-cached system turn;
  - the user turn carries only data, so an offer description cannot act as an
    instruction;
  - budget-gated through `parsing.budget`: out of tokens means no suggestion, not
    a 500 in the middle of a seller filling in a form.

The model returns identifiers only. The regulation level is looked up in our own
registry afterwards — a level invented by a model would be indistinguishable from
one digitized out of a ПКМ.

Service axiom (DEC-dep-owns-commit): flush only — the router owns the commit.
"""

from __future__ import annotations

import decimal
import functools
import json
import logging
import time

import anthropic
import instructor
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.paths import PROMPTS_DIR
from app.core.time import utcnow
from app.domains.compliance import substances as substance_service
from app.domains.compliance.models import SubstanceSuggestion
from app.domains.compliance.substance_match_schemas import SubstanceMatchResult
from app.services import settings_service
from parsing.budget import check_and_reserve_tokens, record_actual_tokens
from parsing.schemas import BudgetExceeded

logger = logging.getLogger(__name__)

_PROMPTS_DIR = PROMPTS_DIR

#: Immutable + versioned, like the other four prompt families. A change means a
#: new `substance_match_v{N+1}.md` and a bump here — the version is journalled
#: on every row so a past suggestion stays explainable.
PROMPT_VERSION = "v1"

#: Conservative pre-reservation; reconciled against real usage after the call.
TOKEN_ESTIMATE = 900

# Module-level singleton clients — built once at import, patched in tests. No
# network at construction, only the API key.
_raw_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
_client = instructor.from_anthropic(_raw_client, mode=instructor.Mode.TOOLS)


@functools.lru_cache(maxsize=4)
def _load_prompt(version: str) -> str:
    path = _PROMPTS_DIR / f"substance_match_{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Substance-match prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def enabled(db: Session) -> bool:
    """Whether the hint is offered at all (runtime kill switch, default on)."""
    return bool(settings_service.get(db, "substance_ai_enabled"))


def _concentration(value: float | None) -> decimal.Decimal | None:
    if value is None:
        return None
    return decimal.Decimal(str(value)).quantize(decimal.Decimal("0.01"))


def suggest(
    db: Session,
    *,
    text: str,
    company_id: int | None = None,
    offer_id: int | None = None,
) -> SubstanceSuggestion | None:
    """Propose a substance for this text and journal the run. Does NOT commit.

    Returns None — with no journal row — when the feature is off, the daily
    token budget is exhausted, or the call fails. All three are "no hint right
    now", and the seller can always pick the substance by hand.
    """
    if not enabled(db):
        return None

    model = str(settings_service.get(db, "llm_extract_model"))
    system_prompt = _load_prompt(PROMPT_VERSION)

    try:
        check_and_reserve_tokens(TOKEN_ESTIMATE)
    except BudgetExceeded:
        logger.warning("substance_ai.budget_exceeded", extra={"company_id": company_id})
        return None

    try:
        started = time.monotonic()
        result, completion = _client.messages.create_with_completion(
            model=model,
            max_tokens=256,
            temperature=0,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": json.dumps({"offer_text": text}, ensure_ascii=False)}
            ],
            response_model=SubstanceMatchResult,
            max_retries=2,
        )
        latency_ms = (time.monotonic() - started) * 1000.0
    except Exception:
        logger.exception("substance_ai.llm_error", extra={"company_id": company_id})
        record_actual_tokens(TOKEN_ESTIMATE, 0)  # release the reservation
        return None

    usage = completion.usage
    tokens_in = usage.input_tokens + getattr(usage, "cache_creation_input_tokens", 0)
    tokens_out = usage.output_tokens
    record_actual_tokens(TOKEN_ESTIMATE, tokens_in + tokens_out)

    # Resolve against OUR registry. A miss is still journalled: the gap is the
    # signal for extending the registry, and dropping it would hide it.
    match = substance_service.resolve(
        db, cas=result.cas, hs_code=result.hs_code, name=result.name
    )

    row = SubstanceSuggestion(
        offer_id=offer_id,
        company_id=company_id,
        input_text=text,
        substance_id=match.id if match else None,
        suggested_name=result.name,
        suggested_cas=result.cas,
        suggested_hs_code=result.hs_code,
        suggested_concentration_pct=_concentration(result.concentration_pct),
        confidence=decimal.Decimal(str(round(result.confidence, 2))),
        model=model,
        prompt_version=PROMPT_VERSION,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    db.add(row)
    db.flush()
    logger.info(
        "substance_ai.suggested",
        extra={
            "suggestion_id": row.id,
            "company_id": company_id,
            "substance_id": row.substance_id,
            "confidence": float(result.confidence),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": round(latency_ms, 1),
        },
    )
    return row


def decide(
    db: Session, suggestion: SubstanceSuggestion, *, accepted: bool, account_id: int
) -> SubstanceSuggestion:
    """Record the seller's answer to a hint. Does NOT commit.

    Only the journal moves here. Whether the offer ends up carrying the
    substance is decided by the offer save that follows — this row is the record
    that a human was asked and answered.
    """
    suggestion.accepted = accepted
    suggestion.decided_at = utcnow()
    suggestion.decided_by_user_account_id = account_id
    db.flush()
    logger.info(
        "substance_ai.decided",
        extra={"suggestion_id": suggestion.id, "accepted": accepted},
    )
    return suggestion


def get_for_company(
    db: Session, suggestion_id: int, company_id: int
) -> SubstanceSuggestion | None:
    """Load a suggestion scoped to the company that asked for it."""
    return (
        db.query(SubstanceSuggestion)
        .filter(
            SubstanceSuggestion.id == suggestion_id,
            SubstanceSuggestion.company_id == company_id,
        )
        .first()
    )
