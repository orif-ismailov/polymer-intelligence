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
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_analyst_or_admin
from app.core.config import settings
from app.core.db import get_db
from app.ingest.registry import list_adapters
from app.models.staff import StaffUser
from app.schemas.admin_settings import SourceBrief, SourceGroup, SourceGroupUpdate
from app.services import source_service
from parsing.budget import per_source_spend

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
    token_spend_7d: int              # Phase 5: 7-day LLM token spend (0 for non-AI sources)


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

    # AI adapter types that consume LLM tokens (REQ-llm-budget: per-source 7-day spend)
    _AI_ADAPTER_PREFIXES: frozenset[str] = frozenset({"telegram_channel", "llm_page"})  # noqa: N806

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
            token_spend_7d=(
                per_source_spend(db, row[0], days=7)
                if any(row[2].startswith(prefix) for prefix in _AI_ADAPTER_PREFIXES)
                else 0
            ),
        )
        for row in rows
    ]


# ── Source reprocess endpoint ─────────────────────────────────────────────────


class ReprocessResult(BaseModel):
    """Result of POST /admin/sources/{id}/reprocess."""

    source_id: int
    adapter: str
    parse_task: str
    requeued: int


@router.post(
    "/sources/{source_id}/reprocess",
    response_model=ReprocessResult,
    summary="Re-parse a source's previously-dropped raw_items",
    description=(
        "Resets this source's raw_items with parse_status 'irrelevant' / 'failed' / "
        "'budget_deferred' back to 'pending' and re-enqueues the adapter's parse task. "
        "Use after fixing a parser so previously-dropped rows become signals — raw_items "
        "are immutable and the parser has a double-parse guard, so they never re-parse on "
        "their own. Already-'parsed' rows are untouched. Admin-only."
    ),
)
def reprocess_source(
    source_id: int,
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReprocessResult:
    """Re-queue a source's previously-dropped raw_items through the correct parse task.

    Raises:
        HTTP 401/403: missing token / non-admin.
        HTTP 404: unknown source_id.
        HTTP 400: the source's adapter has no raw_items → signals parse path
                  (e.g. cbu_rates, which writes fx_rates directly).
    """
    from app.tasks.celery_app import celery_app  # noqa: PLC0415
    from app.tasks.ingest import PARSE_TASK_BY_ADAPTER  # noqa: PLC0415

    row = db.execute(
        sa.text("SELECT id, adapter, config FROM sources WHERE id = :sid"),
        {"sid": source_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    adapter = str(row[1])
    config = row[2] if isinstance(row[2], dict) else {}
    # News-flagged sources use the news classifier regardless of adapter (matches the
    # fetch-time routing in run_source_fetch_isolated).
    if config.get("content_kind") == "news":
        parse_task: str | None = "parse_news_item"
    else:
        parse_task = PARSE_TASK_BY_ADAPTER.get(adapter)
    if parse_task is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reprocess is not supported for adapter '{adapter}'",
        )

    # Reset the previously-dropped rows to pending and collect their ids. The raw_item
    # CONTENT is immutable — only parse_status flips so the double-parse guard re-runs.
    ids = list(
        db.execute(
            sa.text(
                """
                UPDATE raw_items
                SET parse_status = 'pending'
                WHERE source_id = :sid
                  AND parse_status::text IN ('irrelevant', 'failed', 'budget_deferred')
                RETURNING id
                """
            ),
            {"sid": source_id},
        ).scalars()
    )
    db.commit()

    for raw_item_id in ids:
        celery_app.send_task(parse_task, args=[raw_item_id], queue="parse")

    return ReprocessResult(
        source_id=source_id, adapter=adapter, parse_task=parse_task, requeued=len(ids)
    )


# ── LLM spend endpoint (cost visibility) ──────────────────────────────────────

# Approximate list prices, USD per 1M tokens. These are ESTIMATES for a rough $/day
# figure — the response echoes them under `assumed_rates_usd_per_mtok` so they can be
# corrected. Token/call counts below them are exact (journaled in parse_runs).
_RATE_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0},
    "claude-sonnet-4-5": {"in": 3.0, "out": 15.0},
}
_DEFAULT_RATE: dict[str, float] = {"in": 3.0, "out": 15.0}


def _rate_for(model: str) -> dict[str, float]:
    """Best-effort rate lookup: exact, then longest known prefix, else the default."""
    if model in _RATE_USD_PER_MTOK:
        return _RATE_USD_PER_MTOK[model]
    for key, rate in _RATE_USD_PER_MTOK.items():
        if model.startswith(key):
            return rate
    return _DEFAULT_RATE


def _est_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    rate = _rate_for(model)
    return round(tokens_in / 1_000_000 * rate["in"] + tokens_out / 1_000_000 * rate["out"], 4)


class LlmModelSpend(BaseModel):
    """Per-model spend over the window (token/call counts are exact; cost is estimated)."""

    model: str
    calls: int
    tokens_in: int
    tokens_out: int
    est_cost_usd: float


class LlmSpendResponse(BaseModel):
    """LLM spend: today's live budget + a per-model breakdown over the window."""

    today_tokens: int
    daily_limit_tokens: int
    remaining_tokens: int
    pct_used: float
    window_days: int
    total_calls: int
    total_tokens_in: int
    total_tokens_out: int
    est_cost_usd: float
    est_cost_usd_per_day: float
    by_model: list[LlmModelSpend]
    assumed_rates_usd_per_mtok: dict[str, dict[str, float]]


@router.get(
    "/llm-spend",
    response_model=LlmSpendResponse,
    summary="LLM token spend: today's budget + per-model breakdown",
    description=(
        "Today's live token spend vs the daily budget (from the Redis counter) plus a "
        "per-model breakdown over the last `days` days from parse_runs. Token and call "
        "counts are exact; est_cost_usd uses the approximate rates echoed in the response. "
        "Admin-only."
    ),
)
def get_llm_spend(
    days: int = Query(default=7, ge=1, le=90),
    _current_user: StaffUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LlmSpendResponse:
    """Return today's budget usage and a windowed per-model LLM spend breakdown."""
    from parsing.budget import daily_spend  # noqa: PLC0415

    today = daily_spend()
    limit = int(settings.LLM_DAILY_TOKEN_LIMIT)
    remaining = max(0, limit - today)
    pct = round(today / limit * 100, 1) if limit > 0 else 0.0

    rows = db.execute(
        sa.text(
            """
            SELECT model,
                   COUNT(*)                        AS calls,
                   COALESCE(SUM(tokens_in), 0)     AS tokens_in,
                   COALESCE(SUM(tokens_out), 0)    AS tokens_out
            FROM parse_runs
            WHERE created_at >= now() - make_interval(days => :days)
              AND model IS NOT NULL
            GROUP BY model
            ORDER BY (COALESCE(SUM(tokens_in), 0) + COALESCE(SUM(tokens_out), 0)) DESC
            """
        ),
        {"days": days},
    ).fetchall()

    by_model: list[LlmModelSpend] = []
    total_calls = total_in = total_out = 0
    total_cost = 0.0
    for r in rows:
        model, calls, t_in, t_out = str(r[0]), int(r[1]), int(r[2]), int(r[3])
        cost = _est_cost(t_in, t_out, model)
        by_model.append(
            LlmModelSpend(model=model, calls=calls, tokens_in=t_in, tokens_out=t_out, est_cost_usd=cost)
        )
        total_calls += calls
        total_in += t_in
        total_out += t_out
        total_cost += cost

    return LlmSpendResponse(
        today_tokens=today,
        daily_limit_tokens=limit,
        remaining_tokens=remaining,
        pct_used=pct,
        window_days=days,
        total_calls=total_calls,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        est_cost_usd=round(total_cost, 4),
        est_cost_usd_per_day=round(total_cost / days, 4) if days > 0 else 0.0,
        by_model=by_model,
        assumed_rates_usd_per_mtok=_RATE_USD_PER_MTOK,
    )


# ── Source groups (Phase 8f-2) ─────────────────────────────────────────────────────
# Operators organize sources into named groups from the dashboard admin panel.


@router.get("/source-groups", response_model=list[SourceGroup], summary="List source groups")
def list_source_groups(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> list[SourceGroup]:
    return [SourceGroup.model_validate(g) for g in source_service.list_source_groups(db)]


@router.get("/sources/brief", response_model=list[SourceBrief], summary="List sources (identity + group)")
def list_sources_brief(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_analyst_or_admin),
) -> list[SourceBrief]:
    return [SourceBrief.model_validate(s) for s in source_service.list_sources_brief(db)]


@router.put("/sources/{source_id}/group", response_model=SourceBrief, summary="Assign a source's group")
def set_source_group(
    source_id: int,
    body: SourceGroupUpdate,
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_admin),
) -> SourceBrief:
    if not source_service.set_source_group(db, source_id, body.group):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    db.commit()
    source = next((s for s in source_service.list_sources_brief(db) if s["id"] == source_id), None)
    return SourceBrief.model_validate(source)
