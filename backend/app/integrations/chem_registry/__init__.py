"""Chemical-registry integration gateway package (R5 / P5 — T2.5).

The seam a national registry of regulated chemistry would plug into. None exists
today, so the stub knows nothing and the local `substances` table decides.
"""

from __future__ import annotations

from app.integrations.chem_registry.client import (
    MODE_LIVE,
    MODE_STUB,
    ChemRegistryClient,
    ChemRegistryUnavailable,
    StubChemRegistryClient,
    SubstanceLookup,
    current_mode,
    get_chem_registry_client,
)

__all__ = [
    "MODE_LIVE",
    "MODE_STUB",
    "ChemRegistryClient",
    "ChemRegistryUnavailable",
    "StubChemRegistryClient",
    "SubstanceLookup",
    "current_mode",
    "get_chem_registry_client",
]
