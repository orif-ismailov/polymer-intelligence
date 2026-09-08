"""Redis daily rate buckets (R1 W8 — T8.1).

Simple per-subject daily counters (reset at UTC midnight) for abuse-prone portal
actions: company create (per account), document upload (per account), offer create
(per company). Over-limit raises `RateLimited` with a retry-after, which the router
maps to a 429. A generic, reusable helper; `enforce_window` additionally backs the
cabinet's minute-scale sign-in and registration caps.
"""

from __future__ import annotations

import datetime

import redis

# Portal daily limits (bucket → limit). Kept here so the numbers live in one place.
COMPANY_CREATE_PER_DAY = 5
DOCUMENT_UPLOAD_PER_DAY = 30
OFFER_CREATE_PER_DAY = 20
# R2 W6 — per-company buy-side limits (notification endpoints are NOT limited).
INQUIRY_CREATE_PER_DAY = 10
REQUEST_CREATE_PER_DAY = 10
# P5 — the AI substance hint is a paid LLM call a seller can trigger by hand.
# Generous (a form may be re-checked while it is edited) but not unbounded.
SUBSTANCE_SUGGEST_PER_DAY = 50


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


# R3 — counterparty directory search (20/min per account).
DIRECTORY_SEARCH_PER_MIN = 20

# Cabinet auth (0048). Both login buckets are enforced, IP FIRST: on its own the
# per-login counter allows (limit × every login an attacker can name), so the IP cap
# is what makes the pair mean anything. There is no daily bucket on sign-in — an
# account whose owner is genuinely locked out for a day is a support call, and a
# 5-minute window already makes guessing uneconomic.
PORTAL_LOGIN_PER_IP_PER_MIN = 20
PORTAL_LOGIN_PER_ACCOUNT_PER_5MIN = 10
# Registration is anonymous and unverified — no SMS proves the phone — so the IP is
# the only thing to count. Hourly AND daily: the hourly window stops a burst, the
# daily one stops a patient script from filling the staff queue overnight.
PORTAL_REGISTER_PER_IP_PER_HOUR = 5
PORTAL_REGISTER_PER_IP_PER_DAY = 20
PORTAL_PASSWORD_CHANGE_PER_5MIN = 5


def enforce_window(
    redis_client: redis.Redis[str],
    bucket: str,
    subject: str | int,
    limit: int,
    window_seconds: int,
) -> None:
    """Fixed-window counter: `bucket:subject` resets every `window_seconds`."""
    key = f"rl:{bucket}:{subject}"
    count = int(redis_client.incr(key))
    if count == 1:
        redis_client.expire(key, window_seconds)
    if count > limit:
        raw = redis_client.ttl(key)
        ttl = int(raw) if isinstance(raw, int) and raw > 0 else window_seconds
        raise RateLimited(ttl)
