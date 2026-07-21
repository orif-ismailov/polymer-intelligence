"""
/sources API — no-code source constructor wizard endpoints.

Implements the four CRUD operations for the Phase-4 source wizard (REQ-source-builder):
- GET  /sources          : list all sources (health only, never config) [admin/staff read]
- POST /sources          : create a new source from wizard payload [admin]
- POST /sources/{id}/test: run adapter test, set last_test_ok_at on pass [admin]
- PATCH /sources/{id}    : enable/disable source; server-side enable-gate [admin]

Security:
- T-04-21: require_admin on all write endpoints (POST/PATCH/test)
- T-04-22: GET /sources SELECT excludes the config column via sa.text
- T-04-20: PATCH enable-gate: is_enabled=True requires last_test_ok_at IS NOT NULL -> 422

Design (D-04): html_table/rss Test is live (real fetch+parse). telegram_channel/llm_page
Test always returns ok=False ("Available after Phase 5") so they stay is_enabled=False.
The invariant `is_enabled=True ⇒ last_test_ok_at IS NOT NULL` is enforced here.

Pattern reference: 04-PATTERNS.md sources.py section (lines 224–315).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff_user, require_admin
from app.core.db import get_db
from app.models.enums import SourceKind
from app.models.sources import Source
from app.models.staff import StaffUser
from app.schemas.dashboard import (
    SourceCreate,
    SourceDetail,
    SourceHealthItem,
    SourcePatch,
    SourceTestOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])


# ── GET /sources ───────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[SourceHealthItem],
    summary="List sources (health only)",
    description=(
        "Returns per-source identity + health fields for all sources. "
        "Admin or staff read-only. "
        "Security (T-04-22): never returns the config column."
    ),
)
def get_sources(
    _current_user: StaffUser = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
) -> list[SourceHealthItem]:
    """Return health-only view of all sources.

    Security (T-04-22): raw SQL explicitly selects only identity + health fields.
    The config column (which may contain credentials/selectors) is never touched.
    """
    rows = db.execute(
        sa.text(
            """
            SELECT id, name, adapter, kind::text, is_enabled,
                   last_fetch_at, last_success_at, consecutive_failures,
                   last_test_ok_at
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
            last_test_ok_at=row[8],
        )
        for row in rows
    ]


# ── GET /sources/{source_id} (edit form — includes config) ─────────────────────


@router.get(
    "/{source_id}",
    response_model=SourceDetail,
    summary="Get a single source with config (for editing)",
    description=(
        "Full source view INCLUDING config, so an admin can edit the feed URL / "
        "content_kind / selectors. Admin-only (T-04-21) — the health list still hides "
        "config (T-04-22); this is the scoped, single-id exception used by the edit form."
    ),
)
def get_source(
    source_id: int,
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SourceDetail:
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return SourceDetail(
        id=source.id,
        name=source.name,
        adapter=source.adapter,
        kind=source.kind.value if hasattr(source.kind, "value") else str(source.kind),
        country=source.country,
        group_name=source.group_name,
        url=source.url,
        is_enabled=source.is_enabled,
        last_test_ok_at=source.last_test_ok_at,
        config=dict(source.config or {}),
    )


# ── POST /sources ──────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=SourceHealthItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new source (wizard)",
    description=(
        "Create a new source from the wizard payload. "
        "Admin-only (T-04-21). "
        "Config is validated against the adapter's config_schema. "
        "New source is always created with is_enabled=False and last_test_ok_at=NULL."
    ),
)
def create_source(
    body: SourceCreate,
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SourceHealthItem:
    """Create a new source from the wizard.

    Validates config against the adapter's config_schema and creates the
    source with is_enabled=False / last_test_ok_at=NULL (D-04 invariant).

    Raises:
        HTTP 400: Adapter not found in registry.
        HTTP 422: Config does not satisfy the adapter's config_schema.
    """
    from app.ingest.registry import get_adapter  # noqa: PLC0415

    # Validate adapter exists
    try:
        adapter = get_adapter(body.adapter)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown adapter type: {body.adapter!r}",
        ) from None

    # Validate config against adapter's config_schema (422 on pydantic error)
    try:
        adapter.config_schema(**body.config)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid config for adapter {body.adapter!r}: {exc}",
        ) from exc

    # Create source — always disabled, never tested yet
    source = Source(
        adapter=body.adapter,
        name=body.name,
        config=body.config,
        kind=SourceKind.website,           # default for no-code wizard sources
        is_enabled=False,                  # D-04 invariant: must pass test first
        last_test_ok_at=None,              # D-04 invariant: starts NULL
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    logger.info(
        "sources.created",
        extra={"source_id": source.id, "adapter": source.adapter},
    )

    return SourceHealthItem(
        id=source.id,
        name=source.name,
        adapter=source.adapter,
        kind=source.kind.value,
        is_enabled=source.is_enabled,
        last_fetch_at=source.last_fetch_at,
        last_success_at=source.last_success_at,
        consecutive_failures=source.consecutive_failures,
        last_test_ok_at=source.last_test_ok_at,
    )


# ── POST /sources/{source_id}/test ────────────────────────────────────────────


@router.post(
    "/{source_id}/test",
    response_model=SourceTestOut,
    summary="Test a source (run adapter test)",
    description=(
        "Run the adapter test() for the given source. "
        "On pass (ok=True), sets last_test_ok_at to now(UTC). "
        "Returns up to 10 normalized signal-draft rows (D-06). "
        "Admin-only (T-04-21)."
    ),
)
async def test_source(
    source_id: int,
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SourceTestOut:
    """Run adapter test for the source and return the result.

    If test passes (ok=True), sets last_test_ok_at = now(UTC) and commits.
    If test fails (ok=False), last_test_ok_at is NOT modified.

    Security (T-04-20): Pending adapters (telegram_channel/llm_page) always
    return ok=False so last_test_ok_at is never set — enabling these sources
    is impossible via the PATCH enable-gate.
    """
    from app.ingest.registry import get_adapter  # noqa: PLC0415

    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    try:
        adapter = get_adapter(source.adapter)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No adapter registered for type {source.adapter!r}",
        ) from None

    config: dict[str, Any] = dict(source.config or {})
    result = await adapter.test(config)

    if result.ok:
        # D-04: only set last_test_ok_at on actual pass
        source.last_test_ok_at = datetime.datetime.now(tz=datetime.UTC)
        db.commit()

        logger.info(
            "sources.test_passed",
            extra={"source_id": source_id, "adapter": source.adapter},
        )
    else:
        logger.info(
            "sources.test_failed",
            extra={
                "source_id": source_id,
                "adapter": source.adapter,
                "error": result.error,
            },
        )

    return SourceTestOut(
        ok=result.ok,
        sample_rows=result.sample_rows[:10],  # enforce 10-row cap (D-06)
        error=result.error,
    )


# ── PATCH /sources/{source_id} ────────────────────────────────────────────────


@router.patch(
    "/{source_id}",
    response_model=SourceHealthItem,
    summary="Update source (enable/disable)",
    description=(
        "Update source fields. "
        "Enable-gate (T-04-20): is_enabled=True requires last_test_ok_at IS NOT NULL -> 422. "
        "Admin-only (T-04-21)."
    ),
)
def patch_source(
    source_id: int,
    body: SourcePatch,
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SourceHealthItem:
    """Update source fields with server-side enable-gate.

    Security (T-04-20): If body.is_enabled is True and source.last_test_ok_at is None,
    raises 422. This is the critical server-side guard — UI gating is UX-only.
    Pending adapters (telegram_channel/llm_page) can never be enabled because their
    test() always returns ok=False (D-04/D-05).

    Raises:
        HTTP 404: Source not found.
        HTTP 422: Attempting to enable a source that has never passed a test.
    """
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    fields = body.model_fields_set

    # Editing config re-validates against the adapter schema and resets the tested/enabled
    # state — a changed feed must pass a fresh Test before it can be enabled again (D-04).
    config_changed = False
    if "config" in fields and body.config is not None:
        from app.ingest.registry import get_adapter  # noqa: PLC0415

        try:
            adapter = get_adapter(source.adapter)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown adapter type: {source.adapter!r}",
            ) from None
        try:
            adapter.config_schema(**body.config)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid config for adapter {source.adapter!r}: {exc}",
            ) from exc
        config_changed = True
        source.config = dict(body.config)
        source.url = body.config.get("url") or body.config.get("feed_url") or source.url
        source.last_test_ok_at = None  # edited feed must be re-tested
        source.is_enabled = False

    # Enable-gate (T-04-20) — skipped when config was just reset (must re-test first).
    if "is_enabled" in fields and body.is_enabled is not None and not config_changed:
        if body.is_enabled and source.last_test_ok_at is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Source cannot be enabled until a test has passed successfully. "
                    "Run POST /sources/{id}/test first."
                ),
            )
        source.is_enabled = body.is_enabled

    if "name" in fields and body.name:
        source.name = body.name
    if "country" in fields:
        source.country = (body.country.strip() or None) if body.country else None
    if "group_name" in fields:
        source.group_name = (body.group_name.strip() or None) if body.group_name else None

    db.commit()

    logger.info(
        "sources.updated",
        extra={
            "source_id": source_id,
            "is_enabled": source.is_enabled,
        },
    )

    return SourceHealthItem(
        id=source.id,
        name=source.name,
        adapter=source.adapter,
        kind=source.kind.value if hasattr(source.kind, "value") else str(source.kind),
        is_enabled=source.is_enabled,
        last_fetch_at=source.last_fetch_at,
        last_success_at=source.last_success_at,
        consecutive_failures=source.consecutive_failures,
        last_test_ok_at=source.last_test_ok_at,
    )
