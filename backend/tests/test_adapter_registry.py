"""
Unit tests for the SourceAdapter registry (app.ingest.registry).

Covers:
- Registering a dummy adapter and retrieving it by type_name
- Duplicate type_name registration raises ValueError
- Unknown type_name raises KeyError with a useful message
- RawItemDraft and TestResult dataclass contracts
- TestResult.sample_rows is capped at 10 by __post_init__
"""

from __future__ import annotations

import datetime

import pytest

from app.ingest.base import RawItemDraft, SourceAdapter, TestResult
from app.ingest.registry import _clear_registry, get_adapter, list_adapters, register_adapter

# ── Test helpers ────────────────────────────────────────────────────────────────

def _make_dummy_adapter(adapter_type_name: str = "test_dummy") -> object:
    """Build a minimal object satisfying the SourceAdapter Protocol."""
    from pydantic import BaseModel

    class DummyConfig(BaseModel):
        url: str
        page_size: int = 50

    class DummyAdapter:
        config_schema = DummyConfig

        async def fetch(self, source):
            return []

        async def test(self, config: dict) -> TestResult:
            return TestResult(ok=True, sample_rows=[{"id": 1}])

    adapter = DummyAdapter()
    adapter.type_name = adapter_type_name  # type: ignore[attr-defined]
    return adapter


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure each test starts with an empty registry."""
    _clear_registry()
    yield
    _clear_registry()


# ── Registry round-trip ─────────────────────────────────────────────────────────

def test_register_and_get_adapter():
    """register_adapter then get_adapter round-trips by type_name."""
    adapter = _make_dummy_adapter("test_dummy")
    register_adapter(adapter)  # type: ignore[arg-type]
    retrieved = get_adapter("test_dummy")
    assert retrieved is adapter


def test_list_adapters_returns_registered():
    """list_adapters returns all registered adapters."""
    a1 = _make_dummy_adapter("alpha")
    a2 = _make_dummy_adapter("beta")
    register_adapter(a1)  # type: ignore[arg-type]
    register_adapter(a2)  # type: ignore[arg-type]
    adapters = list_adapters()
    assert len(adapters) == 2
    type_names = {a.type_name for a in adapters}
    assert type_names == {"alpha", "beta"}


def test_list_adapters_empty_when_nothing_registered():
    """list_adapters returns an empty list when the registry is empty."""
    assert list_adapters() == []


# ── Duplicate type_name ─────────────────────────────────────────────────────────

def test_duplicate_type_name_raises():
    """Registering two adapters with the same type_name raises ValueError."""
    a1 = _make_dummy_adapter("duplicate")
    a2 = _make_dummy_adapter("duplicate")
    register_adapter(a1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="already registered"):
        register_adapter(a2)  # type: ignore[arg-type]


def test_empty_type_name_raises():
    """Registering an adapter with an empty type_name raises ValueError."""

    class BadAdapter:
        type_name = ""

        async def fetch(self, source):
            return []

        async def test(self, config):
            return TestResult(ok=True)

    with pytest.raises(ValueError, match="type_name must be"):
        register_adapter(BadAdapter())  # type: ignore[arg-type]


# ── Unknown type_name ───────────────────────────────────────────────────────────

def test_get_unknown_adapter_raises_key_error():
    """get_adapter raises KeyError with a descriptive message for unknown type_names."""
    with pytest.raises(KeyError, match="No adapter registered"):
        get_adapter("nonexistent_adapter")


def test_key_error_includes_registered_adapters():
    """KeyError message lists the registered adapters for easy debugging."""
    register_adapter(_make_dummy_adapter("known"))  # type: ignore[arg-type]
    with pytest.raises(KeyError, match="known"):
        get_adapter("nonexistent")


# ── SourceAdapter Protocol ──────────────────────────────────────────────────────

def test_dummy_adapter_satisfies_protocol():
    """The dummy adapter satisfies the SourceAdapter Protocol (runtime check)."""
    adapter = _make_dummy_adapter()
    assert isinstance(adapter, SourceAdapter)


# ── RawItemDraft dataclass ──────────────────────────────────────────────────────

def test_raw_item_draft_fields():
    """RawItemDraft can be constructed with all fields."""
    now = datetime.datetime.now(tz=datetime.UTC)
    draft = RawItemDraft(
        external_id="LOT-001",
        content="<html>...</html>",
        payload={"key": "value"},
        event_at=now,
    )
    assert draft.external_id == "LOT-001"
    assert draft.content == "<html>...</html>"
    assert draft.payload == {"key": "value"}
    assert draft.event_at == now


def test_raw_item_draft_all_none():
    """RawItemDraft accepts None for all optional fields."""
    draft = RawItemDraft(external_id=None, content=None, payload=None, event_at=None)
    assert draft.external_id is None
    assert draft.content is None
    assert draft.payload is None
    assert draft.event_at is None


# ── TestResult dataclass ────────────────────────────────────────────────────────

def test_test_result_ok():
    """TestResult with ok=True and sample rows."""
    result = TestResult(ok=True, sample_rows=[{"id": i} for i in range(5)])
    assert result.ok is True
    assert len(result.sample_rows) == 5
    assert result.error is None


def test_test_result_error():
    """TestResult with ok=False carries an error message."""
    result = TestResult(ok=False, error="Connection refused")
    assert result.ok is False
    assert result.error == "Connection refused"
    assert result.sample_rows == []


def test_test_result_sample_rows_capped_at_10():
    """TestResult caps sample_rows at 10 entries via __post_init__."""
    rows = [{"i": i} for i in range(20)]
    result = TestResult(ok=True, sample_rows=rows)
    assert len(result.sample_rows) == 10
    # First 10 rows are kept
    assert result.sample_rows == [{"i": i} for i in range(10)]


def test_test_result_exactly_10_rows_unchanged():
    """TestResult with exactly 10 rows is not truncated."""
    rows = [{"i": i} for i in range(10)]
    result = TestResult(ok=True, sample_rows=rows)
    assert len(result.sample_rows) == 10
