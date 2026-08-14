"""Portal E-IMZO request/response schemas (R3 Stage A — TA1.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domains.verification.schemas import CaseOut


class ChallengeOut(BaseModel):
    """A freshly minted single-use signing challenge."""

    challenge: str


class VerifyIn(BaseModel):
    """The browser-produced PKCS#7 (base64) over the issued challenge."""

    pkcs7: str = Field(min_length=1)


class VerifyOut(BaseModel):
    """Outcome of an E-IMZO verification (client-safe: no PINFL, only masked holder)."""

    ok: bool
    reason: str | None = None
    holder_masked: str | None = None
    case: CaseOut
