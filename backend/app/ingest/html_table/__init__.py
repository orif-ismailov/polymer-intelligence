"""
html_table adapter package.

Importing this package self-registers the HtmlTableAdapter (html_table)
into the global adapter registry.

Usage:
    import app.ingest.html_table  # registers HtmlTableAdapter as side-effect
"""

from app.ingest.html_table import adapter  # noqa: F401

__all__ = ["adapter"]
