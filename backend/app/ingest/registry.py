"""
SourceAdapter name-keyed registry.

Adapters self-register at import time via register_adapter().
The registry is consumed by:
- GET /admin/source-types (exposes type_name + config_schema for each adapter)
- Celery tasks (look up the right adapter by source.adapter field)

Thread-safety: this module is loaded once per process; the dict is written only at
import time during adapter registration. It is safe for concurrent reads.
"""

from __future__ import annotations

from app.ingest.base import SourceAdapter

# Module-level adapter registry: type_name -> adapter instance
_REGISTRY: dict[str, SourceAdapter] = {}


def register_adapter(adapter: SourceAdapter) -> None:
    """Register an adapter in the name-keyed registry.

    Args:
        adapter: An object satisfying the SourceAdapter Protocol.
            Must have a non-empty ``type_name`` class attribute.

    Raises:
        ValueError: If an adapter with the same type_name is already registered,
            or if the adapter does not have a valid type_name.
    """
    type_name = adapter.type_name
    if not type_name:
        raise ValueError("Adapter type_name must be a non-empty string")
    if type_name in _REGISTRY:
        raise ValueError(
            f"Adapter type_name {type_name!r} is already registered. "
            "Each adapter must have a unique type_name."
        )
    _REGISTRY[type_name] = adapter


def get_adapter(type_name: str) -> SourceAdapter:
    """Retrieve an adapter from the registry by its type_name.

    Args:
        type_name: The adapter's registered type_name key.

    Returns:
        The registered SourceAdapter instance.

    Raises:
        KeyError: If no adapter with the given type_name is registered.
    """
    if type_name not in _REGISTRY:
        registered = sorted(_REGISTRY.keys())
        raise KeyError(
            f"No adapter registered for type_name {type_name!r}. "
            f"Registered adapters: {registered}"
        )
    return _REGISTRY[type_name]


def list_adapters() -> list[SourceAdapter]:
    """Return all registered adapters in registration order.

    Returns:
        A list of all SourceAdapter instances sorted by type_name.
    """
    return list(_REGISTRY.values())


def _clear_registry() -> None:
    """Clear the registry — for testing only.

    Do NOT call this in production code. It is provided so unit tests can
    isolate adapter registration state between test cases.
    """
    _REGISTRY.clear()
