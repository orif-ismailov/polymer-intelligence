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

import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.db import get_db
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


# ── Source health endpoint (REQ-sources-health) ───────────────────────────────


class SourceHealthItem(BaseModel):
    """Per-source health status item for GET /admin/sources/health.

    Security (T-02-21): returns ONLY health + identity fields.
    sources.config / credentials are never included.
    """

    id: int
    name: str
    adapter: str
    kind: str
    is_enabled: bool
    last_fetch_at: datetime.datetime | None
    last_success_at: datetime.datetime | None
    consecutive_failures: int


@router.get(
    "/sources/health",
    response_model=list[SourceHealthItem],
    summary="List per-source health status",
    description=(
        "Returns per-source last_fetch_at, last_success_at, consecutive_failures, "
        "is_enabled, adapter, kind, and id/name. "
        "Admin-only (T-02-21: never exposes sources.config or credentials). "
        "Used by the dashboard Sources screen (REQ-sources-health)."
    ),
)
def get_sources_health(
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[SourceHealthItem]:
    """Return per-source health fields for all sources.

    Security (T-02-21): Only identity + health fields are returned.
    sources.config (which may contain credentials/selectors) is never exposed.

    Raises:
        HTTP 401: No or invalid Bearer token.
        HTTP 403: Valid token but user is not an admin.
    """
    rows = db.execute(
        sa.text(
            """
            SELECT id, name, adapter, kind::text, is_enabled,
                   last_fetch_at, last_success_at, consecutive_failures
            FROM sources
            ORDER BY id
            """
        )
    ).fetchall()

    return [
        SourceHealthItem(
            id=row[0],
            name=row[1],
            adapter=row[2],
            kind=row[3],
            is_enabled=row[4],
            last_fetch_at=row[5],
            last_success_at=row[6],
            consecutive_failures=row[7],
        )
        for row in rows
    ]
