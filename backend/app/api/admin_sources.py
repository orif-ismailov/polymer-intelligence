"""
GET /admin/source-types — adapter config_schema feed for the source constructor.

Returns each registered SourceAdapter's type_name, config_schema (as a
JSON schema dict from pydantic v2 model_json_schema()), and no_code flag.

The no_code flag indicates whether the adapter is intended to be added by
admins via the no-code source constructor (Phase 4) without developer
involvement. Built-in specialized adapters (uzex_*, cbu_rates, sunsirs, dce)
ship pre-configured and are no_code=False; generic adapters (telegram_channel,
llm_page, html_table, rss) are no_code=True — admins can add new sources of
these types via the UI form auto-generated from config_schema.

Reference: docs/polymer-intelligence-dev-spec.md §2.5 adapter table (line 142-146).

Security (T-02-10): endpoint is guarded by require_admin — non-admins get 403.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_admin
from app.ingest.registry import list_adapters
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin", tags=["admin-sources"])

# ── No-code adapter type names (Phase 4 source constructor supports adding these) ──
# Built-in specialized adapters (uzex_*, cbu_rates, sunsirs, dce) are no_code=False.
# Generic adapters that admins can add without developer involvement are no_code=True.
# Reference: SPEC §2.5 adapter table (line 146).
_NO_CODE_TYPE_PREFIXES: frozenset[str] = frozenset(
    {"telegram_channel", "llm_page", "html_table", "rss"}
)


def _is_no_code(type_name: str) -> bool:
    """Return True if this adapter is a no-code type (admin-addable via UI form)."""
    return any(type_name.startswith(prefix) for prefix in _NO_CODE_TYPE_PREFIXES)


class SourceTypeItem(BaseModel):
    """Single item in the GET /admin/source-types response."""

    type_name: str
    config_schema: dict  # type: ignore[type-arg]  # JSON schema dict from pydantic
    no_code: bool


@router.get(
    "/source-types",
    response_model=list[SourceTypeItem],
    summary="List registered adapter types with config schemas",
    description=(
        "Returns all registered SourceAdapter types with their config_schema "
        "(a JSON schema dict from pydantic v2) and no_code flag. "
        "Used by the Phase-4 source constructor to auto-generate add-source forms. "
        "Admin-only (T-02-10)."
    ),
)
def get_source_types(
    _current_user: StaffUser = Depends(require_admin),
) -> list[SourceTypeItem]:
    """Return all registered adapter types with their config_schema.

    The config_schema is the pydantic v2 JSON schema for the adapter's
    config_schema model — used by the no-code source constructor in Phase 4
    to auto-generate the "add source" form fields.

    Raises:
        HTTP 401: No or invalid Bearer token.
        HTTP 403: Valid token but user is not an admin.
    """
    adapters = list_adapters()
    return [
        SourceTypeItem(
            type_name=adapter.type_name,
            config_schema=adapter.config_schema.model_json_schema(),
            no_code=_is_no_code(adapter.type_name),
        )
        for adapter in adapters
    ]
