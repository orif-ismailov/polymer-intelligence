"""
app.ingest.cbu_rates — Official CBU RUz exchange-rate adapter.

Imports the adapter at package load time so the adapter self-registers
in the global registry (DEC-source-adapter-registry).

Usage::

    import app.ingest.cbu_rates  # triggers registration
    from app.ingest.registry import get_adapter
    adapter = get_adapter("cbu_rates")
"""

from app.ingest.cbu_rates.adapter import CbuRateRow, CbuRatesAdapter

__all__ = ["CbuRatesAdapter", "CbuRateRow"]
