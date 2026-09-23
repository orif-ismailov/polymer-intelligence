"""Portal E-IMZO request/response schemas (R3 Stage A — TA1.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domains.verification.schemas import CaseOut


class ChallengeOut(BaseModel):
    """A freshly minted single-use signing challenge."""

    challenge: str


class VerifyIn(BaseModel):
    """Both halves of what `pkcs7.create_pkcs7` returns.

    `signature_hex` is the raw signature value inside the envelope (128 hex chars
    for GOST). The module has always sent it and the bridge has always parsed it;
    nothing read it until verification moved to Didox, whose
    `POST /v1/dsvs/timestamp` takes both and refuses a bare PKCS#7.

    Required rather than optional on purpose: without it the request cannot be
    served at all, and a 422 naming the missing field beats a provider rejection
    two calls downstream that reads like an outage.
    """

    pkcs7: str = Field(min_length=1)
    signature_hex: str = Field(min_length=1)


class VerifyOut(BaseModel):
    """Outcome of an E-IMZO verification (client-safe: no PINFL, only masked holder)."""

    ok: bool
    reason: str | None = None
    holder_masked: str | None = None
    #: The company's case. A verified company re-confirming opens no new one, so
    #: this is its existing case — or None if it was verified without one.
    case: CaseOut | None = None
