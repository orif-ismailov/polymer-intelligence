"""
Phase 5 token-budget Redis gate.

Implements a hard daily token spend limit (REQ-llm-budget) that prevents cost
runaway (AI-SPEC Critical FM#4) without crashing the pipeline. When the daily
budget is exhausted, check_and_reserve_tokens raises BudgetExceeded — the caller
falls back to rule_based_extract and enqueues for nightly LLM catch-up.

Design (AI-SPEC §4 budget.py Core Pattern + §6 G4):
- One Redis key per UTC day: "llm_tokens:YYYY-MM-DD"
- Reservation is a single server-side Lua script (EVAL) that reads the counter,
  checks the limit, and only INCRBYs + sets the midnight EXPIREAT if the
  reservation would keep the total at or below the limit. Because the
  read-check-increment runs as one atomic operation, concurrent prefork workers
  cannot collectively overshoot the cap (CR-05 — no read-modify-write race).
- Rejected reservations never touch the counter, so no rollback is needed.
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

from datetime import UTC, date, datetime

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


def _next_midnight_ts() -> int:
    """Return the UNIX timestamp of the next UTC midnight.

    Used as the EXPIREAT argument so the daily budget key auto-resets.
    """
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    next_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return int(next_midnight.timestamp())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# Atomic compare-and-set reservation. Reads the counter, and only INCRBYs (and
# sets the midnight expiry) if the reservation would keep the total at or below
# the limit. Returns the post-increment total on success, or -1 if the
# reservation was rejected. Running the read-check-increment as a single Redis
# server-side script eliminates the read-modify-write race that allowed N
# concurrent workers to over-spend by up to N reservations (CR-05).
_RESERVE_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
if current + amount > limit then
    return -1
end
local total = redis.call('INCRBY', KEYS[1], amount)
redis.call('EXPIREAT', KEYS[1], tonumber(ARGV[3]))
return total
"""


def check_and_reserve_tokens(estimated_tokens: int) -> None:
    """Atomically check + reserve daily Redis token budget.

    Runs a single server-side Lua script (EVAL) that reads the counter, checks
    the limit, and only INCRBYs (plus sets the midnight EXPIREAT) if the
    reservation would stay at or below DAILY_TOKEN_LIMIT. Because the
    read-check-increment is one atomic operation, concurrent prefork workers
    cannot collectively overshoot the cap.

    Args:
        estimated_tokens: Conservative per-call token estimate. The actual spend
                          is reconciled later by record_actual_tokens().

    Raises:
        BudgetExceeded: The daily limit would be exceeded. Caller must degrade
                        to rule-based fallback and enqueue for nightly catch-up.

    Security (T-05-12 / AI-SPEC G4):
        This is the hard gate preventing cost DoS. The atomic compare-and-set
        guarantees the cap holds under concurrency — no read-modify-write race.
    """
    key = key_for(date.today())
    midnight_ts = _next_midnight_ts()

    result = _redis.eval(
        _RESERVE_LUA,
        1,            # numkeys
        key,          # KEYS[1]
        estimated_tokens,  # ARGV[1]
        DAILY_TOKEN_LIMIT,  # ARGV[2]
        midnight_ts,  # ARGV[3]
    )

    if int(result) < 0:
        current = daily_spend()
        raise BudgetExceeded(
            f"Daily token budget {DAILY_TOKEN_LIMIT:,} exhausted "
            f"(current: {current:,}, requested: {estimated_tokens:,}). "
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


# Refund a full reservation whose LLM call produced no usage (it errored/aborted after
# reserving). DECRBY preserves the daily EXPIREAT; DEL when the counter would go ≤0 so it
# can never drift negative. Prevents a failing API (e.g. billing/credit errors) from
# draining the day's budget one leaked reservation at a time.
_RELEASE_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
if amount <= 0 then return current end
if current <= amount then
    redis.call('DEL', KEYS[1])
    return 0
end
return redis.call('DECRBY', KEYS[1], amount)
"""


def release_reservation(reserved: int) -> None:
    """Return a full token reservation to the daily budget after a failed LLM call.

    Call this ONLY when `check_and_reserve_tokens` succeeded but the subsequent LLM call
    never produced usage (it raised). On the happy path use `record_actual_tokens`
    instead. No-op for a non-positive amount; clamps the counter at 0.

    Args:
        reserved: The estimated_tokens value that was reserved for the failed call.
    """
    if reserved <= 0:
        return
    _redis.eval(_RELEASE_LUA, 1, key_for(date.today()), reserved)


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
    # Import inside function (lazy) so module is importable without a live DB in tests
    from datetime import timedelta

    from sqlalchemy import text as sa_text

    cutoff = datetime.now(tz=UTC) - timedelta(days=days)

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
