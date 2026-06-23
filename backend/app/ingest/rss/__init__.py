"""
rss adapter package.

Importing this package self-registers the RssAdapter (rss)
into the global adapter registry.

Usage:
    import app.ingest.rss  # registers RssAdapter as side-effect
"""

from app.ingest.rss import adapter  # noqa: F401

__all__ = ["adapter"]
