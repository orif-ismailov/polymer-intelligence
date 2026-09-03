"""Didox session + company onboarding (P7.a Stage 2 — W5).

Two facts drive every decision here, both learned on the live contour:

  * **A `user-key` cannot be minted server-side for a customer.** It needs that
    company's own E-IMZO key, in that company's own browser, and it dies after 360
    minutes. So a cache miss is a DOMAIN condition — "ask the user to sign again" —
    not an error, and certainly not a reason to reach for the password path, which
    carries a lockout ladder ending in a permanent block.
  * **Onboarding state cannot be probed.** `GET /v2/documents` answers `200` with an
    empty list whether or not the public offer has been signed, and creating a draft
    succeeds too; the gate only bites on SEND. So the three states are read from
    `didox_companies`, which is why that table exists.

The stub rail is a third case on top: with `didox_mode='stub'` the channel is
DISABLED, and the portal must say nothing at all rather than report a state it never
checked — the same distinction `ChannelDisabled` draws for the registry lookup.
"""

from __future__ import annotations

import datetime

import pytest

from app.domains.edi import onboarding, session


class _Company:
    """Minimal stand-in — these services touch `id` and `tax_id` only."""

    def __init__(self, company_id: int = 7, tax_id: str = "590640341") -> None:
        self.id = company_id
        self.tax_id = tax_id


class _FakeRedis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.writes: list[tuple[str, int, str]] = []

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.writes.append((key, ttl, value))
        self.values[key] = value


class _FakeClient:
    """Records what was called, so "never touches the password path" is testable."""

    def __init__(self, *, token: str = "9a7ec227-9751-4c5e-98fb-442b3edd1e7f") -> None:
        self.token = token
        self.calls: list[str] = []

    def auth_by_eimzo(self, tax_id: str, signature: str, locale: str = "ru") -> str:
        self.calls.append("auth_by_eimzo")
        return self.token

    def auth_by_password(self, tax_id: str, password: str, locale: str = "ru") -> str:
        self.calls.append("auth_by_password")
        return self.token

    def timestamp(self, pkcs7_64: str, signature_hex: str, **kw: object) -> str:
        self.calls.append("timestamp")
        return "TIMESTAMPED"

    def signup(self, signature: str, **kw: object) -> str:
        self.calls.append("signup")
        return self.token

    def offer_base64(self, **kw: object) -> str:
        self.calls.append("offer_base64")
        return "JVBERi0xLjU="

    def create_offer_document(self, document_b64: str, **kw: object) -> str:
        self.calls.append("create_offer_document")
        return "offerdocid"

    def sign_offer(self, signature: str, **kw: object) -> object:
        self.calls.append("sign_offer")
        return object()


# ── the user-key cache ────────────────────────────────────────────────────────


class TestUserKey:
    def test_a_cache_miss_is_a_domain_condition_not_a_password_login(self) -> None:
        """The whole point: we CANNOT mint this key ourselves.

        Falling back to `auth_by_password` here would use OUR service credentials
        to act as somebody else's company, and would spend attempts against a
        ladder whose last rung is permanent.
        """
        client = _FakeClient()
        with pytest.raises(session.UserKeyRequired):
            session.require_user_key(_FakeRedis(), _Company(), client=client)
        assert client.calls == []

    def test_a_cached_key_is_returned_without_touching_the_provider(self) -> None:
        client = _FakeClient()
        redis_client = _FakeRedis({"didox:user_key:590640341": "cached-key"})

        assert session.require_user_key(redis_client, _Company(), client=client) == "cached-key"
        assert client.calls == []

    def test_minting_from_a_signature_caches_below_the_provider_ttl(self) -> None:
        """Didox expires it at 360 minutes; a key that dies mid-request surfaces
        as a 401 the caller cannot tell from a bad token."""
        client = _FakeClient()
        redis_client = _FakeRedis()

        token = session.mint_user_key(
            redis_client,
            _Company(),
            pkcs7_64="PKCS7",
            signature_hex="deadbeef",
            client=client,
        )

        assert token == client.token
        assert client.calls == ["timestamp", "auth_by_eimzo"]
        (key, ttl, value) = redis_client.writes[0]
        assert key == "didox:user_key:590640341"
        assert value == client.token
        assert ttl < 360 * 60

    def test_the_signature_is_timestamped_before_it_is_offered_as_auth(self) -> None:
        """A bare PKCS#7 is rejected by every Didox endpoint that takes a
        `signature`; the TSA token is what auth actually accepts."""
        client = _FakeClient()
        session.mint_user_key(
            _FakeRedis(), _Company(), pkcs7_64="PKCS7", signature_hex="deadbeef", client=client
        )
        assert client.calls.index("timestamp") < client.calls.index("auth_by_eimzo")


# ── onboarding state ──────────────────────────────────────────────────────────


class _Row:
    def __init__(
        self,
        signup_at: datetime.datetime | None = None,
        offer_signed_at: datetime.datetime | None = None,
    ) -> None:
        self.signup_at = signup_at
        self.offer_signed_at = offer_signed_at


NOW = datetime.datetime(2026, 8, 19, tzinfo=datetime.UTC)


class TestOnboardingState:
    def test_no_row_means_we_have_never_seen_this_company_on_didox(self) -> None:
        assert onboarding.state_of(None) == onboarding.NOT_REGISTERED

    def test_signed_up_but_no_offer_is_its_own_state(self) -> None:
        """This is not hypothetical — it is exactly where both of our test
        companies landed when Didox's own registration page 500'd on
        `POST /v1/documents/offer/create` AFTER creating the account."""
        assert onboarding.state_of(_Row(signup_at=NOW)) == onboarding.OFFER_UNSIGNED

    def test_both_stamps_means_ready(self) -> None:
        assert onboarding.state_of(_Row(signup_at=NOW, offer_signed_at=NOW)) == onboarding.READY

    def test_an_offer_stamp_without_a_signup_stamp_is_still_not_ready(self) -> None:
        """Defensive: the two are written by different flows, and a document send
        needs BOTH to have happened."""
        assert onboarding.state_of(_Row(offer_signed_at=NOW)) == onboarding.NOT_REGISTERED


class TestChannelGate:
    def test_the_stub_rail_reports_disabled_rather_than_a_state_it_never_checked(
        self, monkeypatch  # noqa: ANN001
    ) -> None:
        """Saying "not registered" on a deployment with no Didox channel would be
        a claim about a real company's account that nobody looked up. The wizard
        stays silent instead — same rule as `registry_not_configured`."""
        monkeypatch.setattr(onboarding.settings_service, "get", lambda key: "stub")
        assert onboarding.channel_state() == onboarding.DISABLED

    def test_actions_refuse_outright_on_the_stub_rail(self, monkeypatch) -> None:  # noqa: ANN001
        """Reading a state is harmless; sending a legally significant document is
        not, so the ACTIONS raise where the status endpoint merely reports."""
        monkeypatch.setattr(onboarding.settings_service, "get", lambda key: "stub")
        with pytest.raises(onboarding.ChannelDisabled):
            onboarding.assert_live()

    def test_the_live_rail_permits_actions(self, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.setattr(onboarding.settings_service, "get", lambda key: "live")
        onboarding.assert_live()  # must not raise
        assert onboarding.channel_state() is None


# ── routes ────────────────────────────────────────────────────────────────────


def test_the_router_exposes_the_four_onboarding_endpoints() -> None:
    from app.domains.edi.api_portal import router

    paths = {(r.path, tuple(sorted(r.methods))) for r in router.routes}  # type: ignore[attr-defined]
    assert ("/portal/companies/{company_id}/didox/status", ("GET",)) in paths
    assert ("/portal/companies/{company_id}/didox/session", ("POST",)) in paths
    assert ("/portal/companies/{company_id}/didox/signup", ("POST",)) in paths
    assert ("/portal/companies/{company_id}/didox/offer", ("GET",)) in paths
    assert ("/portal/companies/{company_id}/didox/offer", ("POST",)) in paths


def test_the_router_is_mounted() -> None:
    from app.main import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/portal/companies/{company_id}/didox/status" in paths
    assert "/api/v1/portal/companies/{company_id}/didox/offer" in paths


class TestProfileCorroboration:
    """`GET /v1/profile` carries `offerSigned` — the one direct read of step 2.

    Found by re-reading their docs rather than by testing: the original design
    said the state "cannot be probed", which was wrong. It still cannot be RELIED
    on — the endpoint 422s for any company Didox cannot resolve in the tax
    registry — so this corroborates the record, it does not replace it.
    """

    class _Profile:
        def __init__(self, payload: object) -> None:
            self.payload = payload
            self.calls = 0

        def profile(self, *, user_key: str | None = None) -> object:
            self.calls += 1
            if isinstance(self.payload, Exception):
                raise self.payload
            return self.payload

    def _row(self, monkeypatch, payload: object):  # noqa: ANN001, ANN202
        seen: dict[str, str] = {}
        monkeypatch.setattr(
            onboarding, "get_or_create", lambda db, cid, tin: _Row(signup_at=NOW)
        )
        monkeypatch.setattr(
            onboarding, "note_offer_signed", lambda db, cid, tin: seen.setdefault("call", "signed")
        )
        monkeypatch.setattr(
            onboarding, "note_offer_required", lambda db, cid, tin: seen.setdefault("call", "required")
        )
        client = self._Profile(payload)
        onboarding.refresh_from_profile(object(), 7, "590640341", client=client, user_key="k")
        return seen.get("call"), client

    def test_offer_signed_one_marks_it_signed(self, monkeypatch) -> None:  # noqa: ANN001
        call, _ = self._row(monkeypatch, {"offerSigned": 1})
        assert call == "signed"

    def test_offer_signed_zero_corrects_our_record(self, monkeypatch) -> None:  # noqa: ANN001
        call, _ = self._row(monkeypatch, {"offerSigned": 0})
        assert call == "required"

    def test_an_unreadable_profile_changes_nothing(self, monkeypatch) -> None:  # noqa: ANN001
        """A 422 here means "Didox cannot resolve this company", NOT "unsigned".
        Downgrading the record on it would un-onboard a company over an outage."""
        call, client = self._row(monkeypatch, RuntimeError("422 Failed to get Phis By Tin Info"))
        assert call is None
        assert client.calls == 1

    def test_a_profile_without_the_field_changes_nothing(self, monkeypatch) -> None:  # noqa: ANN001
        call, _ = self._row(monkeypatch, {"tin": "590640341"})
        assert call is None
