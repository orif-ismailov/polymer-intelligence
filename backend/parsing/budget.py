"""
Phase 5 token-budget Redis gate.

Implements a hard daily token spend limit (REQ-llm-budget) that prevents cost
runaway (AI-SPEC Critical FM#4) without crashing the pipeline. When the daily
budget is exhausted, check_and_reserve_tokens raises BudgetExceeded — the caller
falls back to rule_based_extract and enqueues for nightly LLM catch-up.

Design (AI-SPEC §4 budget.py Core Pattern + §6 G4):
- One Redis key per UTC day: "llm_tokens:YYYY-MM-DD"
- INCRBY + EXPIREAT in a single pipeline call (atomic: two commands execute
  back-to-back without interleaving; note: Redis pipeline is not a transaction
  unless MULTI/EXEC is used, but INCRBY is atomic per-command so the check
  + rollback is safe under concurrent workers — worst case we over-spend by one
  reservation that gets rolled back before any further spending)
- On budget exceeded: DECRBY to roll back the reservation so the counter
  remains accurate for the next caller
- Expiry is set to UNIX timestamp of UTC midnight so the key auto-resets daily
  without a cron job

Module-level singleton:
  _redis is constructed once at import time from settings.REDIS_URL.
  Tests inject a fake redis by patching parsing.budget._redis.

Usage:
    from parsing.budget import check_and_reserve_tokens, record_actual_tokens, BudgetExceeded

    try:
        check_and_reserve_tokens(estimated_tokens=400)
    except BudgetExceeded:
        # degrade to rule-based, enqueue nightly catch-up
        ...

    # After the LLM call, reconcile the actual spend
    record_actual_tokens(reserved=400, actual=520)  # INCRBY +120
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import redis as redis_lib

from app.core.config import settings
from parsing.schemas import BudgetExceeded

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DAILY_TOKEN_LIMIT: int = settings.LLM_DAILY_TOKEN_LIMIT
"""Hard daily token budget. Sourced from settings.LLM_DAILY_TOKEN_LIMIT (env var)."""

# ---------------------------------------------------------------------------
# Module-level Redis singleton — patched in tests
# ---------------------------------------------------------------------------

_redis: redis_lib.Redis = redis_lib.from_url(  # type: ignore[assignment]
    settings.REDIS_URL,
    decode_responses=False,   # keys are str, values may be bytes
)
"""Redis client — constructed once at import, patched by tests via patch.object."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def key_for(d: date) -> str:
    """Return the daily budget Redis key for a given UTC date.

    Format: "llm_tokens:YYYY-MM-DD"

    Args:
        d: UTC date (use date.today() for the current day).

    Returns:
        str: Redis key, e.g. "llm_tokens:2026-06-18"
    """
    return f"llm_tokens:{d.isoformat()}"


def _seconds_until_midnight() -> int:
    """Return the UNIX timestamp of the next UTC midnight.

    Used as the EXPIREAT argument so the daily budget key auto-resets.
    """
    now = datetime.now(tz=timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Next midnight = today's midnight + 1 day
    next_midnight = midnight.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # If now > midnight, advance to next day
    if now >= next_midnight:
        from datetime import timedelta
        next_midnight = next_midnight + timedelta(days=1)
    return int(next_midnight.timestamp())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_and_reserve_tokens(estimated_tokens: int) -> None:
    """Atomically check + increment the daily Redis token counter.

    Issues INCRBY + EXPIREAT in a pipeline (two atomic per-command operations).
    If the resulting total exceeds DAILY_TOKEN_LIMIT, issues DECRBY to roll back
    the reservation and raises BudgetExceeded.

    Args:
        estimated_tokens: Conservative per-call token estimate (e.g. 400 for a
                          typical extraction call). The actual spend is reconciled
                          later by record_actual_tokens().

    Raises:
        BudgetExceeded: The daily limit would be exceeded. Caller must degrade
                        to rule-based fallback and enqueue for nightly catch-up.

    Security (T-05-12 / AI-SPEC G4):
        This is the hard gate preventing cost DoS. The rollback ensures the counter
        stays accurate even when concurrent workers simultaneously hit the limit.
    """
    key = key_for(date.today())
    midnight_ts = _seconds_until_midnight()

    pipe = _redis.pipeline()
    pipe.incrby(key, estimated_tokens)
    pipe.expireat(key, midnight_ts)
    results = pipe.execute()

    new_total: int = results[0]

    if new_total > DAILY_TOKEN_LIMIT:
        # Roll back the reservation so the counter remains accurate.
        # The next caller will see the pre-reservation total.
        _redis.decrby(key, estimated_tokens)
        raise BudgetExceeded(
            f"Daily token budget {DAILY_TOKEN_LIMIT:,} exhausted "
            f"(current: {new_total - estimated_tokens:,}, "
            f"requested: {estimated_tokens:,}). "
            "Degrade to rule-based fallback and enqueue for nightly catch-up."
        )


def record_actual_tokens(reserved: int, actual: int) -> None:
    """Reconcile the conservative pre-estimate against real token usage.

    Call this after a successful LLM call to correct the counter from the
    estimated reservation to the actual spend. If actual > reserved, INCRBY
    the delta; if actual <= reserved, DECRBY the delta back (or no-op at 0).

    Args:
        reserved: The estimated_tokens value passed to check_and_reserve_tokens().
        actual:   The actual token count from completion.usage.

    Note:
        This function never goes below the reservation minimum — if actual > reserved,
        the full delta is added. If actual <= reserved, the excess reservation is
        returned to the budget.
    """
    key = key_for(date.today())
    delta = actual - reserved

    if delta > 0:
        _redis.incrby(key, delta)
    elif delta < 0:
        # Return the excess reservation to the budget
        _redis.decrby(key, abs(delta))
    # delta == 0: no-op


def daily_spend() -> int:
    """Return the current daily token spend from Redis.

    Returns:
        int: Current value of the daily counter (0 if no tokens have been spent yet).
    """
    key = key_for(date.today())
    value = _redis.get(key)
    if value is None:
        return 0
    return int(value)


def per_source_spend(session: object, source_id: int, days: int = 7) -> int:
    """Return the 7-day rolling token spend for a specific source.

    Queries parse_runs for rows where parser LIKE 'llm_extract%' joined to
    raw_items.source_id, summing tokens_in + tokens_out over the last `days` days.

    This is the per-source spend surfaced in 05-04 (REQ-llm-budget: "per-source
    7-day spend visible"). The AI-SPEC §7 "Per-source token spend" flywheel metric
    drives channel inclusion reviews.

    Args:
        session: SQLAlchemy Session.
        source_id: ID of the source to query.
        days: Rolling window in days (default 7).

    Returns:
        int: Total tokens consumed for this source in the last `days` days.
    """
    from sqlalchemy import text as sa_text

    # Import inside function (lazy) so module is importable without a live DB in tests
    from datetime import timedelta

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

    row = session.execute(  # type: ignore[union-attr]
        sa_text(
            """
            SELECT COALESCE(SUM(pr.tokens_in + pr.tokens_out), 0)
            FROM parse_runs pr
            JOIN raw_items ri ON ri.id = pr.raw_item_id
            WHERE pr.parser LIKE 'llm_extract%'
              AND ri.source_id = :source_id
              AND pr.created_at >= :cutoff
            """
        ),
        {"source_id": source_id, "cutoff": cutoff},
    ).scalar()

    return int(row or 0)
