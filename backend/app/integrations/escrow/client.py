"""Escrow provider gateway (R4 / P3 — T1.3).

The single seam between the payments domain and whatever actually moves money.
Two rails exist by design:

  * **stub** — no provider at all. An operator reconciles against the bank
    statement and marks movement in the dashboard. This is not a placeholder:
    the national bank API is promised but undated, so operator-confirmed escrow
    is a permanent mode of operation.
  * **live** — a bank adapter (P7). Not implemented here. Selecting it raises
    `ProviderUnavailable` rather than silently falling back to the stub, because
    a silent fallback would let an operator believe a bank is confirming
    payments when nothing is.

The rail is a RUNTIME setting (`escrow_mode`, `settings_service._SPECS`), so
switching needs no deploy — and each `EscrowPayment` freezes the mode it was
opened on, so a flip never rewrites how existing rows may be marked.

Shape mirrors `integrations/eimzo/client.py`: a typed protocol, a concrete
implementation, and a factory. P7 adds `LiveEscrowClient` with the timeouts,
circuit breaker (`integrations/circuit_breaker.py`) and `integration_call_log`
rows the eimzo client demonstrates; the domain keeps importing this module only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.services import settings_service

logger = logging.getLogger(__name__)

MODE_STUB = "stub"
MODE_LIVE = "live"


class ProviderUnavailable(Exception):
    """No usable escrow provider for the configured mode."""


@dataclass(frozen=True)
class EscrowOpenResult:
    """What opening an escrow told us. `provider_ref` is the bank's operation id.

    On the stub rail it stays None: an invented reference would make a locally
    marked payment indistinguishable from a bank-confirmed one.
    """

    mode: str
    provider_ref: str | None = None
    #: Free-form payment instructions to show the buyer, when the provider gives
    #: any. The stub gives none — the invoice comes from the bank out of band.
    instructions: str | None = None


@runtime_checkable
class EscrowClient(Protocol):
    """What the payments domain needs from an escrow provider.

    Deliberately narrow. Everything that decides *state* stays in
    `escrow_service`: a provider reports facts, it does not run our state
    machine.
    """

    def open_escrow(self, *, deal_id: int, amount: str, currency: str) -> EscrowOpenResult:
        """Register an escrow for a deal and return the provider's handle."""
        ...

    def get_status(self, provider_ref: str) -> str | None:
        """The provider's own status for a reference, or None when unknown."""
        ...

    def request_release(self, provider_ref: str) -> bool:
        """Ask the provider to pay the seller. True when the request was accepted."""
        ...

    def request_refund(self, provider_ref: str) -> bool:
        """Ask the provider to return the money to the buyer."""
        ...


class StubEscrowClient:
    """The operator rail: records nothing remotely, claims nothing.

    Every method is honest about doing no I/O — `request_release`/`request_refund`
    return False because no bank was asked. The actual movement is asserted by a
    staff member in `escrow_service.mark`, with their id and a mandatory note.
    """

    def open_escrow(self, *, deal_id: int, amount: str, currency: str) -> EscrowOpenResult:
        logger.info(
            "escrow.stub.open",
            extra={"deal_id": deal_id, "amount": amount, "currency": currency},
        )
        return EscrowOpenResult(mode=MODE_STUB, provider_ref=None, instructions=None)

    def get_status(self, provider_ref: str) -> str | None:
        return None

    def request_release(self, provider_ref: str) -> bool:
        return False

    def request_refund(self, provider_ref: str) -> bool:
        return False


def current_mode() -> str:
    """The configured rail, read from `ESCROW_MODE` in `.env`.

    Took a `Session` until the switches moved out of `app_settings`; it
    never queried anything, and a parameter implying a lookup that does
    not happen is the sort of thing that gets copied forward.
    """
    return str(settings_service.get("escrow_mode"))


def get_escrow_client(db: Any) -> EscrowClient:  # noqa: ANN401
    """The client for the configured rail.

    Raises `ProviderUnavailable` for `live` (P7 ships it) and for any value the
    setting should not be able to hold — better a loud 503 than a quiet stub
    standing in for a bank.
    """
    mode = current_mode()
    if mode == MODE_STUB:
        return StubEscrowClient()
    if mode == MODE_LIVE:
        raise ProviderUnavailable(
            "escrow: live mode has no adapter yet (P7) — set escrow_mode=stub"
        )
    raise ProviderUnavailable(f"escrow: unknown mode {mode!r}")
