"""Redis daily rate buckets (R1 W8 — T8.1).

Simple per-subject daily counters (reset at UTC midnight) for abuse-prone portal
actions: company create (per account), document upload (per account), offer create
(per company). Over-limit raises `RateLimited` with a retry-after, which the router
maps to a 429. Mirrors the OTP daily-cap shape but is a generic, reusable helper.
"""

from __future__ import annotations

import datetime

import redis

# Portal daily limits (bucket → limit). Kept here so the numbers live in one place.
COMPANY_CREATE_PER_DAY = 5
DOCUMENT_UPLOAD_PER_DAY = 30
OFFER_CREATE_PER_DAY = 20


class RateLimited(Exception):
    """A daily rate bucket is exhausted. `retry_after` is seconds until reset."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after


def _seconds_until_utc_midnight(now: datetime.datetime) -> int:
    tomorrow = (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((tomorrow - now).total_seconds()))


def enforce_daily(
    redis_client: redis.Redis[str], bucket: str, subject: str | int, limit: int
) -> None:
    """Increment the `bucket:subject` daily counter; raise RateLimited past `limit`."""
    key = f"rl:{bucket}:{subject}"
    count = int(redis_client.incr(key))
    if count == 1:
        redis_client.expire(key, _seconds_until_utc_midnight(datetime.datetime.now(datetime.UTC)))
    if count > limit:
        raw = redis_client.ttl(key)
        ttl = int(raw) if isinstance(raw, int) and raw > 0 else 86400
        raise RateLimited(ttl)
