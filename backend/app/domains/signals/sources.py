"""
Source-group management (Phase 8f-2).

Operators organize sources into named groups (e.g. "Uzbek news", "Global news",
"Exchange") from the dashboard. Grouping is organizational only — it does not change
ingestion. `group_name` is a plain nullable column on sources.

Service axiom (DEC-dep-owns-commit): flush only — the router owns the commit.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domains.signals.source_models import Source


def list_source_groups(db: Session) -> list[dict[str, object]]:
    """Distinct groups with total/active source counts. Ungrouped rows report as '—'."""
    rows = (
        db.execute(
            sa.text(
                """
                SELECT COALESCE(group_name, '') AS group_name,
                       count(*) AS total,
                       count(*) FILTER (WHERE is_enabled) AS active
                FROM sources
                GROUP BY COALESCE(group_name, '')
                ORDER BY group_name ASC
                """
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "group": str(r["group_name"]) or None,
            "total": int(r["total"]),
            "active": int(r["active"]),
        }
        for r in rows
    ]


def list_sources_brief(db: Session) -> list[dict[str, object]]:
    """Identity + group + enabled flag for every source (for the group-assignment UI)."""
    rows = (
        db.execute(
            sa.text(
                """
                SELECT id, name, adapter, country, group_name, is_enabled
                FROM sources
                ORDER BY COALESCE(group_name, 'zzz') ASC, name ASC
                """
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": int(r["id"]),
            "name": str(r["name"]),
            "adapter": str(r["adapter"]),
            "country": r["country"],
            "group_name": r["group_name"],
            "is_enabled": bool(r["is_enabled"]),
        }
        for r in rows
    ]


def set_source_group(db: Session, source_id: int, group: str | None) -> bool:
    """Assign (or clear, when blank/None) a source's group. Returns True if it existed."""
    source = db.get(Source, source_id)
    if source is None:
        return False
    normalized = group.strip() if isinstance(group, str) else None
    source.group_name = normalized or None
    db.flush()
    return True


# ── News scan activity (Phase 8g) ──────────────────────────────────────────────────
# Feeds the dashboard's "what's happening" panel: which news sources exist, when each
# was last scanned, whether it's failing, and how much it produced in the last 24h —
# so the admin can see the result of a "Run parser now" click as the workers complete.


def enabled_rss_source_names(db: Session) -> list[str]:
    """Names of the enabled RSS sources a 'Run parser now' scan will hit."""
    rows = db.execute(
        sa.text("SELECT name FROM sources WHERE is_enabled AND adapter LIKE 'rss%' ORDER BY name")
    ).all()
    return [str(r[0]) for r in rows]


def news_source_activity(db: Session) -> list[dict[str, object]]:
    """Per-source scan status + 24h yield for every news-relevant source.

    News-relevant = RSS / Telegram-channel adapters, or anything flagged
    config.content_kind='news'. Failing/enabled sources sort first.
    """
    rows = (
        db.execute(
            sa.text(
                """
                SELECT s.id AS id, s.name AS name, s.adapter AS adapter,
                       s.group_name AS group_name, s.is_enabled AS is_enabled,
                       s.last_fetch_at AS last_fetch_at, s.last_success_at AS last_success_at,
                       s.consecutive_failures AS consecutive_failures,
                       (SELECT count(*) FROM raw_items ri
                          WHERE ri.source_id = s.id
                            AND ri.fetched_at >= now() - INTERVAL '24 hours') AS raw_24h,
                       (SELECT count(*) FROM signals sig
                          WHERE sig.source_id = s.id AND sig.kind = 'news'
                            AND sig.event_at >= now() - INTERVAL '24 hours') AS news_24h
                FROM sources s
                WHERE s.adapter IN ('rss', 'telegram_channel')
                   OR COALESCE(s.config ->> 'content_kind', '') = 'news'
                ORDER BY s.is_enabled DESC, s.consecutive_failures DESC, s.name ASC
                """
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": int(r["id"]),
            "name": str(r["name"]),
            "adapter": str(r["adapter"]),
            "group_name": r["group_name"],
            "is_enabled": bool(r["is_enabled"]),
            "last_fetch_at": r["last_fetch_at"],
            "last_success_at": r["last_success_at"],
            "consecutive_failures": int(r["consecutive_failures"]),
            "raw_24h": int(r["raw_24h"]),
            "news_24h": int(r["news_24h"]),
        }
        for r in rows
    ]
