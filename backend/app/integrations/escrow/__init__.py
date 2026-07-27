"""Escrow integration gateway package (R4 / P3 — T1.3).

The single seam between the payments domain and whatever moves money. Domain
code imports the client/DTOs from here and never talks to a bank directly.
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
