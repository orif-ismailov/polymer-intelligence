"""
app.ingest — SourceAdapter extension point for data collection.

Public surface exported from this package:
- SourceAdapter  (typing.Protocol, runtime_checkable)
- RawItemDraft   (dataclass returned by adapter.fetch)
- TestResult     (dataclass returned by adapter.test)
- register_adapter, get_adapter, list_adapters  (registry)
- fetch_url, is_safe_url  (hardened HTTP client)

Note: http_client imports are deferred (not at package __init__ level) so that
importing app.ingest.base / app.ingest.registry in tests does not trigger
Settings() validation before the test env patch is applied. Import http_client
directly from app.ingest.http_client when needed.
"""

from app.ingest.base import RawItemDraft, SourceAdapter, TestResult
from app.ingest.registry import get_adapter, list_adapters, register_adapter

__all__ = [
    "SourceAdapter",
    "RawItemDraft",
    "TestResult",
    "register_adapter",
    "get_adapter",
    "list_adapters",
]
