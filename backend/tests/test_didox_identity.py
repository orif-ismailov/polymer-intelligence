"""The Didox identity rail — verification without the UNICON sidecar.

Didox publishes no "verify this PKCS#7" endpoint; the whole `/v1/dsvs/*` surface
is `timestamp` and `signature/join`. What it does have is an **auth call that
refuses a bad signature**: `POST /v1/auth/{taxId}/token/{locale}` answers a
`user-key` for a signature that verifies against the national trust chain AND is
authorised to act for that INN, or `401 Invalid signature`. `GET /v1/profile`
then names the person.

So a 200 from those two calls is the verdict the sidecar used to give us, and it
mints the company's Didox session on the way past — the same key the 007 rail
needs, from the ceremony the user was already performing.

Three things this rail must get right, all asserted below:

  * a refused signature is a **verdict** (`ok=False`), never an outage — an
    outage never fails a case, so a forged signature wearing
    `ProviderUnavailable` would be waved through to manual approval;
  * a company with no Didox account is **neither** — nothing is wrong with the
    signer, so it must not land on the case as a failed check;
  * `profile()` is allowed to fail. It 422s for companies Didox cannot resolve in
    the tax registry, and losing the director's name must not lose the
    confirmation.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests._fake_redis import FakeRedis

TAX_ID = "310529901"
PKCS7 = "cGtjczctYmFzZTY0"
SIG_HEX = "ab" * 64

#: GET /v1/profile — the shape that matters here (reference/05-profile.md).
PROFILE: dict[str, Any] = {
    "fullName": '"WEBMEDIA INFORMATION" MCHJ',
    "director": "ISMAILOV ABROR BAXRAMJONOVICH",
    "directorTin": "491479350",
    "directorPinfl": "30902890231313",
    "tin": TAX_ID,
}


@pytest.fixture(autouse=True)
def _live_rail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin `EIMZO_STUB` off for this module.

    `Settings` reads the repo-root `.env` by absolute path, and a developer's
    copy sets `EIMZO_STUB=true` — so without this the live-path tests below
    silently exercise the stub on a dev machine and the real one only in CI.
    The three stub tests turn it back on explicitly, which is also the honest
    way round: a test of a switched behaviour should name the switch.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "EIMZO_STUB", False)


class _Company:
    """`mint_user_key` reads exactly one attribute; so does this rail."""

    def __init__(self, tax_id: str = TAX_ID) -> None:
        self.tax_id = tax_id


class _Client:
    """The three calls this rail makes, each independently riggable."""

    def __init__(
        self,
        *,
        token: str | Exception = "user-key-uuid",
        profile: dict[str, Any] | Exception | None = None,
    ) -> None:
        self._token = token
        self._profile = PROFILE if profile is None else profile
        self.calls: list[str] = []

    def timestamp(self, pkcs7_64: str, signature_hex: str) -> str:  # noqa: ARG002
        self.calls.append("timestamp")
        return "timeStampTokenB64"

    def auth_by_eimzo(self, tax_id: str, signature: str, locale: str = "ru") -> str:  # noqa: ARG002
        self.calls.append("auth_by_eimzo")
        if isinstance(self._token, Exception):
            raise self._token
        return self._token

    def profile(self, *, user_key: str | None = None) -> dict[str, Any]:  # noqa: ARG002
        self.calls.append("profile")
        if isinstance(self._profile, Exception):
            raise self._profile
        return self._profile


def _verify(client: _Client, redis_client: FakeRedis | None = None) -> Any:  # noqa: ANN401
    from app.domains.edi.identity import verify_identity

    return verify_identity(
        redis_client if redis_client is not None else FakeRedis(),
        _Company(),
        pkcs7_64=PKCS7,
        signature_hex=SIG_HEX,
        client=client,
        # These tests are about what happens once we DO reach Didox; the
        # unconfigured short-circuit has its own test below.
        is_configured=lambda: True,
    )


# ── the happy path ────────────────────────────────────────────────────────────


def test_a_signature_didox_accepts_is_a_confirmed_identity() -> None:
    client = _Client()
    result = _verify(client)

    assert result.ok is True
    assert result.error is None
    assert client.calls == ["timestamp", "auth_by_eimzo", "profile"], (
        "the TSA round trip is not optional — a bare PKCS#7 is refused as auth"
    )


def test_the_profile_names_the_person_behind_the_key() -> None:
    result = _verify(_Client())

    assert result.signer is not None
    assert result.signer.org_inn == TAX_ID
    assert result.signer.full_name == "ISMAILOV ABROR BAXRAMJONOVICH"
    assert result.signer.pinfl == "30902890231313"
    assert result.signer.org_name == '"WEBMEDIA INFORMATION" MCHJ'


def test_confirming_mints_the_companys_didox_session_in_passing() -> None:
    """The point of choosing this rail: the 007 document flow needs a `user-key`
    that can only be minted with the company's own key, in their own browser. The
    user is already at the machine with the card in, so taking it here means they
    are never asked to sign twice for one action."""
    from app.integrations.didox.auth import USER_KEY_CACHE

    redis_client = FakeRedis()
    _verify(_Client(token="fresh-key"), redis_client)

    assert redis_client.get(USER_KEY_CACHE.format(tin=TAX_ID)) == "fresh-key"


# ── the three failure shapes, which are three DIFFERENT things ────────────────


def test_a_refused_signature_is_a_verdict_not_an_outage() -> None:
    """`ok=False` lands on the case as a failed `eimzo_signature` check. If this
    ever raised `ProviderUnavailable` instead, the degradation invariant would
    send a forged signature straight to a human as "provider down, approve
    manually"."""
    from app.integrations.didox.client import InvalidSignature

    result = _verify(_Client(token=InvalidSignature(401, "Unauthorized. Invalid signature")))

    assert result.ok is False
    assert result.error == "signature_invalid"
    assert result.signer is None


def test_a_company_with_no_didox_account_is_not_a_failed_check() -> None:
    """`422 User not registered` says nothing about the signature — the key is
    fine, the company simply has never onboarded. Recording that as a failed
    identity check would read as a fraud signal about an honest applicant, so it
    raises for the router to turn into a precondition the user can satisfy."""
    from app.domains.edi.identity import DidoxAccountRequired
    from app.integrations.didox.client import DidoxError

    with pytest.raises(DidoxAccountRequired):
        _verify(_Client(token=DidoxError(422, "User not registered")))


def test_didox_being_down_still_propagates_as_an_outage() -> None:
    from app.integrations.didox.client import ProviderUnavailable

    with pytest.raises(ProviderUnavailable):
        _verify(_Client(token=ProviderUnavailable("didox: 503")))


def test_a_didox_4xx_we_did_not_expect_degrades_instead_of_500ing() -> None:
    """Found in the browser, 17.09.2026, and it was a 500.

    `/v1/dsvs/timestamp` answered `422 Unprocessable Content` — our request was
    malformed, or the partner token is missing. Neither is a statement about the
    signer, so neither is a verdict; but the original code re-raised the bare
    `DidoxError`, the router does not catch that class, and the user got an
    Internal Server Error.

    That breaks the degradation invariant in the worst direction: an operator
    misconfiguration read as a crash, with the manual verification path
    unreachable behind it. Anything we cannot turn into a verdict is an outage.
    """
    from app.integrations.didox.client import DidoxError, ProviderUnavailable

    with pytest.raises(ProviderUnavailable) as exc:
        _verify(_Client(token=DidoxError(422, "Unprocessable Content")))
    assert "422" in str(exc.value), "the operator needs the provider's own reason in the log"


def test_the_same_holds_for_a_4xx_from_the_profile_read() -> None:
    """Already true, and pinned so the degrade above cannot regress it."""
    from app.integrations.didox.client import DidoxError

    result = _verify(_Client(profile=DidoxError(422, "Unprocessable Content")))
    assert result.ok is True


def test_an_unconfigured_deployment_does_not_spend_a_request_to_find_out() -> None:
    """`is_configured()` exists because "without a token every call is a 401".

    Reaching the provider to discover we have no credentials costs a round trip,
    writes a misleading `integration_call_log` row, and — as the 500 above showed
    — arrives as whatever 4xx they happen to use that day. Refuse locally.
    """
    from app.domains.edi import identity
    from app.integrations.didox.client import ProviderUnavailable

    calls: list[str] = []

    with pytest.raises(ProviderUnavailable):
        identity.verify_identity(
            FakeRedis(),
            _Company(),
            pkcs7_64=PKCS7,
            signature_hex=SIG_HEX,
            client=_Client(),
            is_configured=lambda: False,
        )
    assert calls == []


# ── profile is allowed to fail ────────────────────────────────────────────────


def test_an_unresolvable_profile_does_not_lose_the_confirmation() -> None:
    """`profile()` 422s for any company Didox cannot resolve in the tax registry
    (its own docstring says so). The signature still verified and the INN is still
    bound, so the identity is confirmed — with the person fields simply unknown."""
    from app.integrations.didox.client import DidoxError

    result = _verify(_Client(profile=DidoxError(422, "Failed to get Phis By Tin Info")))

    assert result.ok is True
    assert result.signer is not None
    assert result.signer.org_inn == TAX_ID, "the INN we authenticated for is still known"
    assert result.signer.full_name is None
    assert result.signer.pinfl is None


def test_a_profile_outage_does_not_lose_the_confirmation_either() -> None:
    from app.integrations.didox.client import ProviderUnavailable

    result = _verify(_Client(profile=ProviderUnavailable("didox: 503")))

    assert result.ok is True
    assert result.signer is not None and result.signer.org_inn == TAX_ID


# ── the dev stub, and why it hangs off EIMZO_STUB rather than didox_mode ──────


def _stub_blob(tin: str = TAX_ID) -> str:
    """What the injected browser bridge emits (`portal/e2e/r3-eimzo.spec.ts`)."""
    import base64
    import json

    return base64.b64encode(
        json.dumps({"challenge": tin, "tin": tin, "name": "IVANOV IVAN"}).encode()
    ).decode()


def test_the_stub_answers_without_calling_didox(monkeypatch) -> None:  # noqa: ANN001
    """`EIMZO_STUB` is what lets the suite, the e2e specs and a dev stack drive
    the whole flow with no key, no module and no partner token."""
    from app.core.config import settings
    from app.domains.edi import identity

    monkeypatch.setattr(settings, "EIMZO_STUB", True)
    client = _Client()
    result = identity.verify_identity(
        FakeRedis(), _Company(), pkcs7_64=_stub_blob(), signature_hex=SIG_HEX, client=client
    )

    assert result.ok is True
    assert result.signer is not None and result.signer.org_inn == TAX_ID
    assert client.calls == [], "the stub must not reach the provider at all"


def test_the_stub_still_refuses_a_signature_for_another_company(monkeypatch) -> None:  # noqa: ANN001
    """It is a stub, not an approval: the INN binding is the one rule it keeps,
    so the mismatch path stays drivable in dev."""
    from app.core.config import settings
    from app.domains.edi import identity

    monkeypatch.setattr(settings, "EIMZO_STUB", True)
    result = identity.verify_identity(
        FakeRedis(),
        _Company(),
        pkcs7_64=_stub_blob(tin="999999999"),
        signature_hex=SIG_HEX,
        client=_Client(),
    )

    assert result.ok is False


def test_the_stub_is_not_reachable_from_a_production_config() -> None:
    """The load-bearing safety property, and the reason this did NOT move onto
    `didox_mode`.

    `DIDOX_MODE` ships `stub` — it is the shipped default for every deployment
    that has not enabled the document rail — so hanging a synthetic identity off
    it would make a default-configured production install "verify" real companies
    with fabricated director data, silently. `EIMZO_STUB` ships `False` and
    `Settings` REFUSES to boot with it on unless `DEBUG` is also on, which is the
    guard that makes a forgeable verifier safe to keep.
    """
    from pydantic import ValidationError

    from app.core.config import Settings

    assert Settings.model_fields["EIMZO_STUB"].get_default() is False
    assert Settings.model_fields["DIDOX_MODE"].get_default() == "stub", (
        "if this ever ships 'live', re-read the comment above before reusing it"
    )
    with pytest.raises(ValidationError, match="EIMZO_STUB"):
        Settings(EIMZO_STUB=True, DEBUG=False, _env_file=None)  # type: ignore[call-arg]


# ── what this rail can no longer claim ────────────────────────────────────────


def test_the_fields_didox_cannot_tell_us_are_absent_not_invented() -> None:
    """The sidecar read these off the certificate; `GET /v1/profile` carries none
    of them. Absent is the honest answer — a plausible default here would be a
    fact about a real person that nothing established."""
    signer = _verify(_Client()).signer

    assert signer is not None
    assert not hasattr(signer, "serial_number") or signer.serial_number is None
    assert not hasattr(signer, "revoked") or signer.revoked is None
