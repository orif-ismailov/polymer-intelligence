"""
SourceAdapter Protocol + transfer dataclasses.

All concrete adapters (UZEX, CBU, Telegram, etc.) implement this Protocol.
The registry (registry.py) indexes adapters by type_name.

Key design decisions:
- SourceAdapter is a runtime_checkable Protocol so adapters need no base class.
- RawItemDraft is a dataclass (not a pydantic model) — it lives only in worker
  memory; persistence is in raw_items (models/sources.py).
- TestResult.sample_rows MUST be capped at 10 by adapters — this is the
  Test-button preview contract for the admin add-source wizard (Phase 4).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.domains.signals.source_models import Source


@dataclass
class RawItemDraft:
    """A single data item returned by adapter.fetch before dedup+persist.

    Fields mirror the raw_items table columns (see models/sources.py).
    - external_id: source-side identifier (UZEX lot#, Telegram msg_id, etc.)
    - content: plain-text or HTML fragment for LLM extraction
    - payload: structured data (JSON) as-is from the source
    - event_at: when the event occurred at the source (UTC); None if unknown
    """

    external_id: str | None
    content: str | None
    payload: dict[str, object] | None
    event_at: datetime.datetime | None


@dataclass
class TestResult:
    """Result of adapter.test(config) — used by the Test button in the UI.

    - ok: whether the test completed without error
    - sample_rows: up to 10 rows from the source (MUST be capped at 10 by adapters)
    - error: human-readable error message if ok=False; None if ok=True
    """

    ok: bool
    sample_rows: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None

    def __post_init__(self) -> None:
        # Enforce the 10-row cap here so callers don't need to remember it
        if len(self.sample_rows) > 10:
            self.sample_rows = self.sample_rows[:10]


@runtime_checkable
class SourceAdapter(Protocol):
    """Protocol that all data source adapters must satisfy.

    Class-level attributes:
    - type_name: unique registry key (e.g. 'uzex_offers', 'cbu_rates')
    - config_schema: a pydantic BaseModel subclass defining the fields that
      the admin fills in when creating a source of this type; used by
      GET /admin/source-types to auto-generate the add-source form (Phase 4).

    Methods:
    - fetch(source) -> list[RawItemDraft]: pull data from the live source
    - test(config) -> TestResult: validate config and return sample rows
    """

    type_name: str
    config_schema: type[BaseModel]

    async def fetch(self, source: Source) -> list[RawItemDraft]:
        """Fetch new items from the source. Returns a list of RawItemDraft objects."""
        ...

    async def test(self, config: dict[str, object]) -> TestResult:
        """Test the given config. Returns TestResult with ok/error and up to 10 sample rows."""
        ...
