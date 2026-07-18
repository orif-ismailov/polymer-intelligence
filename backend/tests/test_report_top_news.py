"""
Tests for Phase 7d — ranked Top-News snapshot + rendering from ai.news.

_snapshot_top_news ranks kind='news' signals by importance then recency and groups
them into themed buckets; render_markdown surfaces them. DB is mocked.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock


def _news_row(headline: str, importance: str, category: str, impact: str, when: int, source: str = "OilNews", country: str = "UZ") -> dict:
    return {
        "event_at": datetime.datetime(2026, 7, 18, 8, when, 0, tzinfo=datetime.UTC),
        "source_name": source,
        "country": country,
        "ai": {
            "news": {
                "headline": headline,
                "category": category,
                "importance": importance,
                "market_impact": impact,
                "summary": f"why {headline} matters",
                "companies": ["ACME"],
                "country": country,
            }
        },
    }


def _db_returning(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = rows
    return db


def test_top_news_ranked_by_importance_then_recency() -> None:
    from app.services.report_service import _snapshot_top_news

    rows = [
        _news_row("Low but newest", "low", "polymers", "neutral", when=59),
        _news_row("High older", "high", "plant_shutdown", "negative", when=10),
        _news_row("Medium", "medium", "oil", "positive", when=30),
    ]
    out = _snapshot_top_news(_db_returning(rows))

    assert out["count"] == 3
    headlines = [a["headline"] for a in out["top"]]
    assert headlines[0] == "High older"       # high beats newer-low
    assert headlines[1] == "Medium"
    assert headlines[2] == "Low but newest"
    # JSON-safe: no datetime leaks into the snapshot
    assert all("_rank" not in a for a in out["top"])


def test_top_news_themes_grouping() -> None:
    from app.services.report_service import _snapshot_top_news

    rows = [
        _news_row("Plant halts", "high", "plant_shutdown", "negative", when=10),
        _news_row("New PP line", "high", "new_projects", "positive", when=20),
        _news_row("Diesel up", "medium", "oil", "positive", when=30),
    ]
    out = _snapshot_top_news(_db_returning(rows))
    themes = out["themes"]
    assert "Plant halts" in themes["shutdowns"]
    assert "New PP line" in themes["projects"]
    assert "Diesel up" in themes["energy"]


def test_render_includes_top_news_and_themes() -> None:
    from app.services.report_service import render_markdown

    snapshot = {
        "date": "2026-07-18",
        "products": [],
        "top_news": {
            "count": 2,
            "top": [
                {"headline": "Shurtan PP outage", "importance": "high", "market_impact": "negative", "source": "PetroTG"},
                {"headline": "New methanol plant", "importance": "medium", "market_impact": "positive", "source": "GovUZ"},
            ],
            "themes": {"shutdowns": ["Shurtan PP outage"], "projects": ["New methanol plant"]},
        },
    }
    md = render_markdown(snapshot, "summary text", "forecast text")

    assert "📰 *Топ новостей (24ч)*" in md
    assert "Shurtan PP outage" in md
    assert "🔴📉" in md                       # high + negative markers
    assert "🛑 *Остановки и ремонты*" in md   # themed bucket rendered
    assert "🏭 *Заводы, проекты, инвестиции*" in md


def test_render_without_top_news_is_unchanged() -> None:
    from app.services.report_service import render_markdown

    md = render_markdown({"date": "2026-07-18", "products": []}, "s", None)
    assert "📰 *Топ новостей" not in md       # section skipped when absent
    assert "🤖 *AI Summary*" in md
