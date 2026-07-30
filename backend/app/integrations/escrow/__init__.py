"""Escrow integration gateway package (R4 / P3 — T1.3; R6 / P7.b).

The single seam between the payments domain and whatever moves money. Domain
code imports the client/DTOs from here and never talks to a bank directly.

Two halves, and only one of them needs the bank to exist:

  * `client` — OUTBOUND (open an escrow, ask a status, request a release). The
    live implementation waits on the partner bank's specification; `live` mode
    raises `ProviderUnavailable` rather than falling back to the stub.
  * `events` — INBOUND. A bank's callback normalized into our own vocabulary by
    a per-provider mapper. Written against our shape rather than any bank's, so
    it ships complete: adding a real bank is one mapper function.
"""

from __future__ import annotations

from app.integrations.escrow.client import (
    MODE_LIVE,
    MODE_STUB,
    EscrowClient,
    EscrowOpenResult,
    ProviderUnavailable,
    StubEscrowClient,
    current_mode,
    get_escrow_client,
)

__all__ = [
    "MODE_LIVE",
    "MODE_STUB",
    "EscrowClient",
    "EscrowOpenResult",
    "ProviderUnavailable",
    "StubEscrowClient",
    "current_mode",
    "get_escrow_client",
]
