"""State-registry integration gateway (R6 / P7.c).

The seam between company verification and the state registries. Domain code
imports the DTOs and the factory from here and never talks to a registry
directly.

Ships as an interface + stub: the only official realtime channel for a private
organisation is ПЦД, and that access does not exist yet. The channel that works
today is not a client — it is an operator reading an open service and recording a
`registry_snapshots` row with `source='manual'`. Both produce the same DTOs, so
the verification checks judge them with identical code.
"""

from __future__ import annotations

from app.integrations.gov_registry.client import (
    COMPANY_ACTIVE,
    COMPANY_LIQUIDATED,
    COMPANY_SUSPENDED,
    COMPANY_UNKNOWN,
    MODE_DIDOX,
    MODE_LIVE,
    MODE_STUB,
    CompanySnapshot,
    GovRegistryClient,
    LicenseSnapshot,
    ProviderUnavailable,
    StubGovRegistryClient,
    VatSnapshot,
    company_from_payload,
    current_mode,
    get_gov_registry_client,
    license_from_payload,
    licenses_from_payload,
    licenses_payload,
    vat_from_payload,
)

__all__ = [
    "COMPANY_ACTIVE",
    "COMPANY_LIQUIDATED",
    "COMPANY_SUSPENDED",
    "COMPANY_UNKNOWN",
    "MODE_DIDOX",
    "MODE_LIVE",
    "MODE_STUB",
    "CompanySnapshot",
    "GovRegistryClient",
    "LicenseSnapshot",
    "ProviderUnavailable",
    "StubGovRegistryClient",
    "VatSnapshot",
    "company_from_payload",
    "current_mode",
    "get_gov_registry_client",
    "license_from_payload",
    "licenses_from_payload",
    "licenses_payload",
    "vat_from_payload",
]
