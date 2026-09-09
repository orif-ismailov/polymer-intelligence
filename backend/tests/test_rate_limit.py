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


def test_window_over_limit_raises() -> None:
    from app.services import rate_limit  # noqa: PLC0415

    fake = FakeRedis()
    for _ in range(3):
        rate_limit.enforce_window(fake, "portal_login_ip", "10.0.0.1", 3, 60)
    with pytest.raises(rate_limit.RateLimited):
        rate_limit.enforce_window(fake, "portal_login_ip", "10.0.0.1", 3, 60)


class TestRateLimitDisabled:
    """`RATE_LIMIT_ENABLED=false` must silence every bucket, not just the daily ones.

    Both primitives, because they back different subjects: `enforce_window` is what
    caps registration per IP and `enforce_daily` what caps company/tender creation
    per account and per company. A switch that reached only one of them would leave
    a regression run blocked on the half nobody thought to check.
    """

    def test_enforce_daily_is_a_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.config import settings  # noqa: PLC0415
        from app.services import rate_limit  # noqa: PLC0415

        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        fake = FakeRedis()
        for _ in range(50):
            rate_limit.enforce_daily(fake, "company_create", 1, 5)

    def test_enforce_window_is_a_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.config import settings  # noqa: PLC0415
        from app.services import rate_limit  # noqa: PLC0415

        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        fake = FakeRedis()
        for _ in range(50):
            rate_limit.enforce_window(fake, "portal_register_ip", "89.249.62.214", 5, 3600)

    def test_no_redis_key_is_written(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returning BEFORE the INCR, not swallowing RateLimited after it.

        A counter incremented while the switch was off would still be sitting there,
        already past its limit, the moment the switch went back on.
        """
        from app.core.config import settings  # noqa: PLC0415
        from app.services import rate_limit  # noqa: PLC0415

        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        fake = FakeRedis()
        rate_limit.enforce_daily(fake, "company_create", 1, 5)

        assert fake.get("rl:company_create:1") is None
