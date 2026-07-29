"""Chemical-registry gateway (R5 / P5 — T2.5).

The seam a live national registry would plug into. Unlike the escrow gateway —
where a bank API is promised, only undated — **no machine-readable registry of
regulated chemistry exists in Uzbekistan**: the law on chemical safety is a draft
(УП-224), and НРОХВ (chemical-safety.uz) is announced but empty. Our own
`substances` table is the source of truth, and that is an architectural decision.

So this module exists for exactly one reason: when a registry does appear, P7
adds a `LiveChemRegistryClient` here and `offer_compliance_service` does not
change. The stub answers "I know nothing" — it never fabricates a level, because
a fabricated `free` reads exactly like a real one.

Shape mirrors `integrations/escrow/client.py`: protocol, implementation, factory,
and a runtime `chem_registry_mode` setting so switching needs no deploy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.services import settings_service

logger = logging.getLogger(__name__)

MODE_STUB = "stub"
MODE_LIVE = "live"


class ChemRegistryUnavailable(Exception):
    """No usable chemical-registry provider for the configured mode."""


@dataclass(frozen=True)
class SubstanceLookup:
    """What an external registry told us about one substance."""

    hs_code: str
    name: str
    #: A `regulation_level` value when the registry states one; None when it
    #: only confirms the substance exists.
    regulation_level: str | None = None
    source: str | None = None


@runtime_checkable
class ChemRegistryClient(Protocol):
    """What the compliance domain would ask an external registry."""

    def lookup_substance(
        self, *, hs_code: str | None = None, name: str | None = None
    ) -> SubstanceLookup | None:
        """Look a substance up, or None when the registry does not know it."""
        ...


class StubChemRegistryClient:
    """Knows nothing, and says so.

    Returning None (rather than a `free` verdict) keeps the local registry the
    only thing that can say a substance is unregulated.
    """

    def lookup_substance(
        self, *, hs_code: str | None = None, name: str | None = None
    ) -> SubstanceLookup | None:
        logger.debug("chem_registry.stub.lookup", extra={"hs_code": hs_code, "name": name})
        return None


def current_mode(db: Any) -> str:  # noqa: ANN401 — Session, typed loosely to stay import-light
    """The configured rail (`stub` | `live`) from the runtime settings."""
    return str(settings_service.get(db, "chem_registry_mode"))


def get_chem_registry_client(db: Any) -> ChemRegistryClient:  # noqa: ANN401
    """The client for the configured rail.

    `live` raises until P7 ships an adapter: a silent fallback to the stub would
    make "the registry had nothing" indistinguishable from "we never asked".
    """
    mode = current_mode(db)
    if mode == MODE_STUB:
        return StubChemRegistryClient()
    if mode == MODE_LIVE:
        raise ChemRegistryUnavailable(
            "chem_registry: live mode has no adapter yet (P7) — set chem_registry_mode=stub"
        )
    raise ChemRegistryUnavailable(f"chem_registry: unknown mode {mode!r}")
