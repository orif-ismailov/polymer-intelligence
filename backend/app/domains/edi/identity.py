"""Identity confirmation through Didox — the rail that replaced the sidecar.

Verifying a national PKCS#7 is not something stock crypto libraries can do, so
until now every signature in this product was checked by the UNICON
`e-imzo-server` sidecar. That sidecar is licensed, was never obtained, and runs
nowhere — which left company confirmation, contract signing and the sample letter
all answering 503 outside a dev stack with `EIMZO_STUB=true`.

**Didox verifies signatures as a side effect of authenticating them.** It
publishes no verify endpoint — `/v1/dsvs/*` is `timestamp` and `signature/join`,
neither of which returns a verdict — but `POST /v1/auth/{taxId}/token/{locale}`
answers a `user-key` only for a signature that verifies against the national
trust chain AND belongs to a certificate authorised to act for that INN. A 200 is
therefore the same statement the sidecar used to make, from a provider we already
hold a partner token for. `GET /v1/profile` then names the person behind the key.

The INN binding is free here and used to cost us a comparison: Didox refuses the
signature *for that taxId*, so a certificate belonging to another company cannot
mint a key at all.

### What this rail cannot say, and must not pretend to

  * **Freshness.** The signed content is the company's INN, not our single-use
    nonce, so nothing in the signature proves it was made just now. Callers keep
    their own challenge as a single-use guard on OUR side; it is no longer a
    claim about the envelope, and `contracts.eimzo` says so where it pops one.
  * **Certificate serial, validity window, revocation.** `GET /v1/profile`
    carries none of them. They are absent rather than defaulted — a plausible
    value here would be a fact about a real person that nothing established.

### Three outcomes, deliberately three different shapes

| Didox | Meaning | Here |
|---|---|---|
| 200 | the signature verifies for this INN | `ok=True` + signer |
| 401 | it does not | `ok=False`, `error='signature_invalid'` — a VERDICT |
| 422 `User not registered` | no Didox account yet | `DidoxAccountRequired` |
| any other 4xx | our request, or our credentials | `ProviderUnavailable` |
| 5xx / timeout | Didox is down | `ProviderUnavailable` propagates |

Row four is the one that cost a 500. A `422 Unprocessable Content` from
`/v1/dsvs/timestamp` is not a statement about the signer — it means our payload
was wrong or the partner token is missing — so re-raising the bare `DidoxError`
sent an operator misconfiguration to the user as an Internal Server Error, with
the manual verification path unreachable behind it. **Anything that is not a
verdict is an outage**: the user is told to try again or go manual, and the
operator gets the provider's own reason in the log.

The first two rows are the load-bearing distinction. A verdict lands on the case
as a failed check; an outage must never fail a case (the degradation invariant
that keeps manual verification usable). Collapsing a refused signature into
`ProviderUnavailable` would hand a forged one to a human captioned "provider
unavailable, approve manually", so the split is enforced one layer down by
`InvalidSignature` and asserted in `tests/test_didox_identity.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.core.config import settings
from app.domains.edi.session import mint_user_key
from app.integrations.didox.client import (
    DidoxError,
    InvalidSignature,
    ProviderUnavailable,
    get_didox_client,
)
from app.integrations.didox.client import is_configured as _is_configured

if TYPE_CHECKING:  # pragma: no cover
    import redis

    from app.domains.companies.models import Company

logger = logging.getLogger(__name__)


class _Verifier(Protocol):
    """The slice of `DidoxClient` this rail needs — keeps the tests honest.

    A superset of `session._Minter`, so one of these can be handed straight to
    `mint_user_key`; the extra member is the profile read that names the signer.
    """

    def timestamp(self, pkcs7_64: str, signature_hex: str) -> str: ...
    def auth_by_eimzo(self, tax_id: str, signature: str, locale: str = ...) -> str: ...
    #: `Mapping[str, object]`, not `dict[str, Any]`: `app.domains.*` bans explicit
    #: `Any`, and `object` is the honest type for untrusted provider JSON anyway —
    #: every read goes through `_text`, which narrows it.
    def profile(self, *, user_key: str | None = ...) -> Mapping[str, object]: ...


#: Didox's own words for "this company has no account here". Matched as a
#: substring because the sentence is theirs to reword and is not a code.
_NOT_REGISTERED = "not registered"


class DidoxAccountRequired(Exception):
    """The signature was never judged: this company has no Didox account.

    Deliberately not a verdict. Nothing is wrong with the certificate or the
    person holding it, so this must not reach the case as a failed
    `eimzo_signature` check — that reads as a fraud signal about an honest
    applicant. `/v1/auth/signup` (`reference/02-registration.md`) is the door out,
    which makes this a precondition the user can satisfy rather than a refusal.
    """

    def __init__(self, tax_id: str) -> None:
        super().__init__(f"no didox account for {tax_id}")
        self.tax_id = tax_id


@dataclass(frozen=True)
class DidoxSigner:
    """Who Didox says is behind the key.

    Shaped to match the `EimzoSigner` this replaces, so the domain code changed at
    the seam only. `position` is absent for a reason: the sidecar read the
    certificate's `T` field, whereas `GET /v1/profile` reports the company's
    registered DIRECTOR — a different claim that happens to be true of the same
    person most of the time. Left `None` until something actually establishes it.
    """

    org_name: str | None = None
    org_inn: str | None = None
    full_name: str | None = None
    pinfl: str | None = None
    position: str | None = None


@dataclass(frozen=True)
class DidoxIdentityResult:
    """`ok` is Didox's verdict on the signature; `error` names a refusal."""

    ok: bool
    signer: DidoxSigner | None = None
    error: str | None = None


def verify_identity(
    redis_client: redis.Redis[str] | None,
    company: Company,
    *,
    pkcs7_64: str,
    signature_hex: str,
    client: _Verifier | None = None,
    is_configured: Callable[[], bool] | None = None,
) -> DidoxIdentityResult:
    """Confirm who signed, by asking Didox to authenticate them as `company`.

    Mints and caches the company's `user-key` on success — the session the 007
    document rail needs, taken from the ceremony the user was already performing
    rather than asked for again later.

    Raises `DidoxAccountRequired` and `ProviderUnavailable`; every other outcome
    is a `DidoxIdentityResult`.
    """
    if settings.EIMZO_STUB:
        return _stub_identity(company, pkcs7_64)

    # Refuse locally rather than spending a round trip to be told we have no
    # credentials — which arrives as whatever 4xx they use that day, and writes an
    # `integration_call_log` row implying we tried something meaningful.
    configured = is_configured or _is_configured
    if not configured():
        raise ProviderUnavailable("didox: no partner token configured")

    didox = client or get_didox_client()
    try:
        token = mint_user_key(
            redis_client, company, pkcs7_64=pkcs7_64, signature_hex=signature_hex, client=didox
        )
    except InvalidSignature as exc:
        # The verdict. Logged at info: a refused signature is an ordinary answer,
        # and an operator reading warnings should see outages, not typos.
        logger.info(
            "didox.identity.refused", extra={"tax_id": company.tax_id, "reason": str(exc)}
        )
        return DidoxIdentityResult(ok=False, error="signature_invalid")
    except DidoxError as exc:
        if _NOT_REGISTERED in (exc.message or "").lower():
            raise DidoxAccountRequired(company.tax_id) from exc
        # Any other 4xx is OUR request or OUR credentials — never a fact about the
        # signer. Re-raising it bare made the router, which catches
        # `ProviderUnavailable`, miss it entirely and answer 500.
        logger.warning(
            "didox.identity.rejected_our_request",
            extra={"tax_id": company.tax_id, "error": str(exc)},
        )
        raise ProviderUnavailable(str(exc)) from exc

    return DidoxIdentityResult(ok=True, signer=_signer_for(company, token, didox))


def _stub_identity(company: Company, pkcs7_64: str) -> DidoxIdentityResult:
    """Dev/CI identity, with no provider and no key.

    **Why this stays on `EIMZO_STUB` and did NOT move onto `didox_mode='stub'`.**
    `DIDOX_MODE` ships `stub` — it is the default for every deployment that has
    not switched the document rail on — so hanging a synthetic identity off it
    would make a default-configured production install confirm real companies
    with fabricated director data, and nothing on screen would say so.
    `EIMZO_STUB` ships `False` and `Settings` refuses to boot with it on unless
    `DEBUG` is on too (`_reject_eimzo_stub_outside_debug`), which is exactly the
    guard a forgeable verifier needs. The two switches answer different
    questions: one is "does this deployment file documents", the other is "is
    this a developer's machine".

    Reuses the sidecar's `_stub_verify`, so the envelope the e2e bridge emits and
    the real-PKCS#7 branch (`local_verify`) both keep working unchanged. The
    challenge it matches against is now the INN, because that is what the browser
    signs on this rail — the same string on both sides.
    """
    from app.integrations.eimzo.client import _stub_verify  # noqa: PLC0415 — dev-only path

    result = _stub_verify(pkcs7_64, company.tax_id)
    if not result.ok:
        return DidoxIdentityResult(ok=False, error=result.error or "signature_invalid")
    signer = result.signer
    return DidoxIdentityResult(
        ok=True,
        signer=DidoxSigner(
            org_name=signer.org_name if signer else None,
            org_inn=(signer.org_inn if signer else None) or company.tax_id,
            full_name=signer.full_name if signer else None,
            pinfl=signer.pinfl if signer else None,
            position=signer.position if signer else None,
        ),
    )


def _signer_for(company: Company, token: str, didox: _Verifier) -> DidoxSigner:
    """Name the person behind `token`, falling back to what we already know.

    `GET /v1/profile` answers `422 "Failed to get Phis By Tin Info info from
    soliq"` for any company Didox cannot resolve in the tax registry, and it can
    be down like anything else. Neither may cost us the confirmation: the
    signature verified and the INN is bound whatever the profile says, so a
    failure here degrades to a signer carrying only the INN we authenticated for.
    """
    try:
        payload = didox.profile(user_key=token)
    except (DidoxError, ProviderUnavailable) as exc:
        logger.warning(
            "didox.identity.profile_unavailable",
            extra={"tax_id": company.tax_id, "error": str(exc)},
        )
        return DidoxSigner(org_inn=company.tax_id)

    return DidoxSigner(
        org_name=_text(payload.get("fullName")),
        # Didox echoes the company it authenticated; ours is the INN it accepted
        # the signature FOR, which is the one the case is about.
        org_inn=_text(payload.get("tin")) or company.tax_id,
        full_name=_text(payload.get("director")),
        pinfl=_text(payload.get("directorPinfl")),
    )


def _text(value: object) -> str | None:
    """Trim to None. Didox pads several profile fields, and `directorPinfl`
    arrives as an int in at least one documented response."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        return None
    return value.strip() or None
