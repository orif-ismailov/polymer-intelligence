"""Didox EDI gateway (R6 / P7.a).

Domain code imports from here and never talks to `api-partners.didox.uz`
directly. Two things live behind this barrel:

  * **`client`** — the partner-API HTTP gateway (circuit breaker,
    `integration_call_log`, the 4xx/5xx split). Stage 1 wires the tax-registry
    lookup and the catalogs; the document rail follows.
  * **`registry`** — that lookup adapted onto P7.c's existing `GovRegistryClient`
    protocol, so company verification gains a real channel without a second
    subsystem.

The partner token is a **server-side secret**: it identifies us as an integrator
and must never reach a browser. See `~/.claude/skills/didox` for the mirrored API
documentation this was written against.
"""

from app.integrations.didox.auth import service_user_key
from app.integrations.didox.client import (
    PROD_BASE_URL,
    TEST_BASE_URL,
    DidoxClient,
    DidoxCompanyInfo,
    DidoxError,
    ProviderUnavailable,
    get_didox_client,
    is_configured,
)
from app.integrations.didox.registry import (
    CompanyNotFound,
    DidoxGovRegistryClient,
    normalize_status,
    to_company_snapshot,
    to_vat_snapshot,
)

__all__ = [
    "PROD_BASE_URL",
    "TEST_BASE_URL",
    "CompanyNotFound",
    "DidoxClient",
    "DidoxCompanyInfo",
    "DidoxError",
    "DidoxGovRegistryClient",
    "ProviderUnavailable",
    "get_didox_client",
    "is_configured",
    "normalize_status",
    "service_user_key",
    "to_company_snapshot",
    "to_vat_snapshot",
]
