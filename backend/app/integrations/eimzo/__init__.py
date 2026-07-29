"""E-IMZO integration gateway package (R3 — ARCHITECTURE §9.6, §12).

The single seam between verification/contract domain code and the UNICON
e-imzo-server sidecar. Domain code imports `verify_pkcs7` / the DTOs from here and
never talks to the sidecar or handles national O'zDSt crypto directly.
"""

from __future__ import annotations

from app.integrations.eimzo.client import (
    EimzoClient,
    EimzoSigner,
    EimzoVerifyResult,
    ProviderUnavailable,
    get_eimzo_client,
    verify_pkcs7,
)

__all__ = [
    "EimzoClient",
    "EimzoSigner",
    "EimzoVerifyResult",
    "ProviderUnavailable",
    "get_eimzo_client",
    "verify_pkcs7",
]
