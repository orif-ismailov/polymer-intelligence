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

from app.models.sources import Source


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
