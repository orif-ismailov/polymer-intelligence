"""
xarid (UZEX public procurement) adapter package.

Importing this package self-registers the ``xarid_tenders`` adapter into the global
adapter registry.

Usage:
    import app.ingest.xarid  # registers the xarid_tenders adapter as a side-effect
"""

from app.ingest.xarid import adapters  # noqa: F401

__all__ = ["adapters"]
