"""Unit tests for the daily rate buckets (R1 W8 — T8.1)."""

from __future__ import annotations

import pytest

from tests._fake_redis import FakeRedis


def test_under_limit_does_not_raise() -> None:
    from app.services import rate_limit  # noqa: PLC0415

    fake = FakeRedis()
    for _ in range(5):
        rate_limit.enforce_daily(fake, "company_create", 1, 5)


def test_over_limit_raises_with_retry_after() -> None:
    from app.services import rate_limit  # noqa: PLC0415

    fake = FakeRedis()
    for _ in range(5):
        rate_limit.enforce_daily(fake, "company_create", 1, 5)
    with pytest.raises(rate_limit.RateLimited) as exc:
        rate_limit.enforce_daily(fake, "company_create", 1, 5)
    assert exc.value.retry_after > 0


def test_buckets_are_per_subject() -> None:
    from app.services import rate_limit  # noqa: PLC0415

    fake = FakeRedis()
    for _ in range(5):
        rate_limit.enforce_daily(fake, "offer_create", "companyA", 5)
    # a different subject shares neither counter nor the limit
    rate_limit.enforce_daily(fake, "offer_create", "companyB", 5)
