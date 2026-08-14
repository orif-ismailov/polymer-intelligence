"""
Request AI analysis service (Phase 5).

Analyses a buyer purchase request with the LLM and stamps the result into
``requests.ai`` so the dashboard request-detail "AI-анализ" panel shows real
match_score / demand_level / recommendation instead of Phase-4 placeholders.

Design mirrors parsing/extractor.py (the signal extractor):
  - instructor + Anthropic, Mode.TOOLS, structured Pydantic output, temperature 0.
  - A versioned, prompt-cached system prompt; user turn carries ONLY data (the request
    + market context) so request text can't act as instructions (T-05-10 analog).
  - Budget-gated via parsing.budget (reserve estimate → reconcile actual). On
    BudgetExceeded the request is left un-analysed (panel keeps placeholders) rather
    than crashing the caller.

Service axiom: builds the ai dict and sets request.ai, calls db.flush(), but NEVER
commits — the caller (Celery task or router) owns the transaction.
"""

from __future__ import annotations

import datetime
import decimal
import functools
import logging
import time

import anthropic
import instructor
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.paths import PROMPTS_DIR
from app.models.requests import Request
from app.schemas.request_analysis import RequestAnalysisResult
from app.services import price_analysis_service
from parsing.budget import check_and_reserve_tokens, record_actual_tokens
from parsing.schemas import BudgetExceeded

logger = logging.getLogger(__name__)

_PROMPTS_DIR = PROMPTS_DIR

# Module-level singleton clients — constructed once at import, patched in tests
# (AI-SPEC Pitfall 1). Construction needs no network, only the API key from settings.
# NOTE: no explicit annotations — instructor.Instructor resolves to Any under
# ignore_missing_imports, which app.services' disallow_any_explicit would reject.
_raw_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
_client = instructor.from_anthropic(_raw_client, mode=instructor.Mode.TOOLS)


@functools.lru_cache(maxsize=8)
def _load_prompt(version: str) -> str:
    """Load the analyze_request_{version}.md system prompt (cached)."""
    path = _PROMPTS_DIR / f"analyze_request_{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Request-analysis prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _build_market_context(db: Session, request: Request) -> dict[str, object]:
    """Assemble the structured market context fed to the LLM for one request.

    Read-only: recent comparable seller offers for the product + the D-02 price
    comparison against the local market average. No db writes.
    """
    def _f(v: decimal.Decimal | float | int | None) -> float | None:
        return float(v) if v is not None else None

    # A free-typed product (product_id is NULL) has no catalog row, comparable offer
    # set, or price series — analyse it on its text fields alone (no market block).
    pid = request.product_id
    product_code: str | None = None
    product_name: str | None = None
    market: dict[str, object] = {
        "recent_offer_count_30d": 0,
        "offer_avg_price": None,
        "offer_min_price": None,
        "offer_max_price": None,
        "latest_offer_at": None,
    }
    price_analysis: dict[str, float | str] | None = None

    if pid is not None:
        product_row = db.execute(
            sa.text("SELECT code, name_ru FROM products WHERE id = :pid"),
            {"pid": pid},
        ).fetchone()
        product_code = product_row[0] if product_row else None
        product_name = product_row[1] if product_row else None

        # Recent seller offers for this product (last 30 days) — supply liquidity signal.
        offers = (
            db.execute(
                sa.text(
                    """
                    SELECT count(*)                      AS n,
                           avg(price)                     AS avg_price,
                           min(price)                     AS min_price,
                           max(price)                     AS max_price,
                           max(event_at)                  AS latest_at
                    FROM signals
                    WHERE product_id = :pid
                      AND kind = 'sell_offer'
                      AND event_at >= now() - interval '30 days'
                    """
                ),
                {"pid": pid},
            )
            .mappings()
            .one()
        )
        market = {
            "recent_offer_count_30d": int(offers["n"] or 0),
            "offer_avg_price": _f(offers["avg_price"]),
            "offer_min_price": _f(offers["min_price"]),
            "offer_max_price": _f(offers["max_price"]),
            "latest_offer_at": (
                offers["latest_at"].isoformat() if offers["latest_at"] else None
            ),
        }

        price_analysis = price_analysis_service.compute_price_analysis(
            db, pid, request.target_price, request.currency
        )

    return {
        "request": {
            "product_code": product_code,
            "product_name": product_name,
            "grade_text": request.grade_text,
            "polymer_type": request.polymer_type,
            "volume": _f(request.volume),
            "volume_unit": request.volume_unit,
            "target_price": _f(request.target_price),
            "currency": request.currency,
            "incoterms": request.incoterms.value if request.incoterms else None,
            "destination_country": request.destination_country,
            "port_or_city": request.port_or_city,
            "comment": request.comment,
        },
        "market": market,
        "price_analysis": price_analysis,
    }


def analyze_request(db: Session, request: Request) -> dict[str, object] | None:
    """Analyse one request with the LLM and stamp the result into request.ai.

    Returns the ai dict written (also assigned to request.ai), or None when analysis
    is skipped (feature disabled) or deferred (budget exhausted). Does NOT commit.
    """
    if not settings.REQUEST_AI_ANALYSIS_ENABLED:
        return None

    import json  # noqa: PLC0415

    model = settings.REQUEST_AI_ANALYSIS_MODEL
    prompt_version = settings.REQUEST_AI_ANALYSIS_PROMPT_VERSION
    estimate = settings.REQUEST_AI_TOKEN_ESTIMATE

    context = _build_market_context(db, request)
    system_prompt = _load_prompt(prompt_version)

    try:
        check_and_reserve_tokens(estimate)
    except BudgetExceeded:
        # Leave request un-analysed; the panel keeps honest placeholders. The trader
        # can re-trigger after the daily budget resets.
        logger.warning(
            "request_analysis.budget_exceeded",
            extra={"request_id": request.id},
        )
        return None

    try:
        t0 = time.monotonic()
        result, completion = _client.messages.create_with_completion(
            model=model,
            max_tokens=512,
            temperature=0,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
            response_model=RequestAnalysisResult,
            max_retries=2,
        )
        latency_ms = (time.monotonic() - t0) * 1000.0
    except Exception:
        logger.exception(
            "request_analysis.llm_error", extra={"request_id": request.id}
        )
        record_actual_tokens(estimate, 0)  # release the reservation
        return None

    usage = completion.usage
    tokens_in = usage.input_tokens + getattr(usage, "cache_creation_input_tokens", 0)
    tokens_out = usage.output_tokens
    record_actual_tokens(estimate, tokens_in + tokens_out)

    ai_block: dict[str, object] = {
        "match_score": round(result.match_score, 3),
        "demand_level": result.demand_level,
        "recommendation": result.recommendation.strip(),
        "analyzed_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
        "model": model,
        "prompt_version": prompt_version,
    }

    request.ai = ai_block
    db.flush()

    logger.info(
        "request_analysis.done",
        extra={
            "request_id": request.id,
            "match_score": ai_block["match_score"],
            "demand_level": ai_block["demand_level"],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": round(latency_ms, 1),
        },
    )
    return ai_block
