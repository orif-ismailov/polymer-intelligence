"""One Didox answer per company, reused by everything that needs it.

A single registration used to ask Didox for the same tax-registry record at least
three times — the step-2 prefill, then the `gov_registry` check, then the
`vat_status` check — and all three answers are the same JSON: one
`/v1/utils/info/{tin}` record carries both the company and its VAT code. On
23.09.2026 the White Rock registration made EIGHT such calls in twelve minutes,
and the VAT check spent five attempts fetching a field the prefill had already
received in its first second. Each redundant call is another chance to meet a
Didox timeout, and each one counts against the monthly quota.

So `fetch_info` keeps what it learned in Redis for a day. Checks still judge what
the SERVER received from Didox — never anything the browser sent back — they just
stop asking again for it. A day is safe here: liquidating a company in Uzbekistan
takes more than a month.

The second half is the wiring, which is where the bug actually lived: the check
path built its client WITHOUT Redis. That meant no cache, and also that the
service `user-key` could not be cached either — so every registry check logged in
to Didox with the platform's password, and a rejected password could not set the
cooldown that stands between us and Didox's permanent lockout.
"""

from __future__ import annotations

import datetime

import pytest

from tests._fake_redis import FakeRedis
from tests.test_didox_client import INFO_FOUND


class _Didox:
    """A Didox client that counts how often the registry is asked."""

    def __init__(self, payload: dict[str, object] | None = INFO_FOUND) -> None:
        self.payload = payload
        self.calls = 0

    def info_by_tin(self, tin: str, *, user_key: str | None = None):  # noqa: ANN201, ARG002
        from app.integrations.didox.client import DidoxCompanyInfo  # noqa: PLC0415

        self.calls += 1
        return DidoxCompanyInfo.from_payload(self.payload)


class _BrokenRedis(FakeRedis):
    def get(self, key: str) -> str | None:
        raise ConnectionError("redis down")

    def setex(self, key: str, seconds: int, value: object) -> bool:
        raise ConnectionError("redis down")


def _client(didox: _Didox, redis: FakeRedis | None):  # noqa: ANN202
    from app.integrations.didox.registry import DidoxGovRegistryClient  # noqa: PLC0415

    return DidoxGovRegistryClient(didox, user_key="k", redis_client=redis)  # type: ignore[arg-type]


class TestOneCallPerCompany:
    def test_a_second_lookup_of_the_same_tin_does_not_call_didox(self) -> None:
        didox, redis = _Didox(), FakeRedis()
        _client(didox, redis).fetch_info("310529901")
        _client(didox, redis).fetch_info("310529901")
        assert didox.calls == 1

    def test_the_prefill_answer_serves_both_checks(self) -> None:
        """Three consumers, three client instances, one registry call — the
        registration's actual shape (prefill, then gov_registry, then vat_status)."""
        didox, redis = _Didox(), FakeRedis()
        client = _client
        client(didox, redis).fetch_info("310529901")    # step 2 prefill
        client(didox, redis).lookup_company("310529901")  # gov_registry check
        client(didox, redis).lookup_vat("310529901")    # vat_status check
        assert didox.calls == 1

    def test_a_different_tin_is_its_own_lookup(self) -> None:
        didox, redis = _Didox(), FakeRedis()
        _client(didox, redis).fetch_info("310529901")
        _client(didox, redis).fetch_info("310857605")
        assert didox.calls == 2

    def test_the_cached_record_is_the_record(self) -> None:
        """Every field survives the round trip — including the date, which a naive
        JSON dump turns into a string that `companies.registration_date` would
        then refuse at insert time."""
        didox, redis = _Didox(), FakeRedis()
        fresh = _client(didox, redis).fetch_info("310529901")
        cached = _client(didox, redis).fetch_info("310529901")
        assert cached == fresh
        assert isinstance(cached.registered_at, datetime.date)
        assert cached.vat_reg_code == "326080220838"

    def test_it_is_kept_for_a_day(self) -> None:
        from app.integrations.didox import registry  # noqa: PLC0415

        redis = FakeRedis()
        _client(_Didox(), redis).fetch_info("310529901")
        ttl = redis.ttl(registry.INFO_CACHE_KEY.format(tin="310529901"))
        assert registry.INFO_CACHE_TTL_SECONDS == 24 * 60 * 60
        assert 0 < ttl <= registry.INFO_CACHE_TTL_SECONDS


class TestWhatIsNotCached:
    def test_not_found_is_asked_again(self) -> None:
        """A company registered this morning may reach the registry this afternoon;
        caching its absence for a day would hide it for a day."""
        from app.integrations.gov_registry import ProviderUnavailable  # noqa: PLC0415

        didox, redis = _Didox(payload={"tin": None, "name": None}), FakeRedis()
        for _ in range(2):
            with pytest.raises(ProviderUnavailable):
                _client(didox, redis).fetch_info("999999999")
        assert didox.calls == 2

    def test_no_redis_means_no_cache_not_an_error(self) -> None:
        didox = _Didox()
        _client(didox, None).fetch_info("310529901")
        _client(didox, None).fetch_info("310529901")
        assert didox.calls == 2

    def test_a_broken_redis_falls_back_to_didox(self) -> None:
        """Redis is an optimisation here. It must never be the reason a lookup
        fails — the registry answer is what matters."""
        didox = _Didox()
        info = _client(didox, _BrokenRedis()).fetch_info("310529901")
        assert info.tin == "310529901"
        assert didox.calls == 1

    def test_a_corrupt_cache_entry_is_ignored(self) -> None:
        from app.integrations.didox import registry  # noqa: PLC0415

        didox, redis = _Didox(), FakeRedis()
        redis.setex(registry.INFO_CACHE_KEY.format(tin="310529901"), 60, "{not json")
        info = _client(didox, redis).fetch_info("310529901")
        assert info.tin == "310529901"
        assert didox.calls == 1


class TestTheCheckPathIsWired:
    def test_the_verification_checks_get_a_redis_client(self, monkeypatch) -> None:  # noqa: ANN001
        """The actual bug. Without this the cache above exists and the checks never
        see it — and the service user-key is re-minted with our password on every
        check, with no cooldown to stop a rejected password walking us into
        Didox's permanent lockout."""
        from app.core import redis as core_redis  # noqa: PLC0415
        from app.integrations import gov_registry  # noqa: PLC0415
        from app.integrations.didox import registry  # noqa: PLC0415
        from tests.conftest import set_switch  # noqa: PLC0415

        shared = FakeRedis()
        monkeypatch.setattr(core_redis, "cache_client", lambda: shared)
        monkeypatch.setattr(registry, "get_didox_client", lambda: _Didox())
        set_switch(gov_registry_mode="didox", didox_partner_token="test-token")

        client = gov_registry.get_gov_registry_client(None)

        assert isinstance(client, registry.DidoxGovRegistryClient)
        assert client._redis is shared  # noqa: SLF001
