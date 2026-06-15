"""
UZEX adapter package.

Importing this package self-registers all three UZEX adapters
(uzex_offers, uzex_contracts, uzex_deals) into the global adapter registry.

Usage:
    import app.ingest.uzex  # registers all UZEX adapters as side-effect
"""

from app.ingest.uzex import adapters  # noqa: F401

__all__ = ["adapters"]
