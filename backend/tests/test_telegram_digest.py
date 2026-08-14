"""
Tests for Phase 7e — the compact Telegram channel digest (render_telegram_digest).

Distinct from render_markdown (the archival report body): this push is news-forward,
hard-capped at 1500 chars, and always carries the "Powered by IMEX AI" footer. Pure
function over the snapshot dict — no DB, no network.
"""

from __future__ import annotations


def _news(headline: str, importance: str = "high", impact: str = "negative", source: str = "OilTG") -> dict:
    return {"headline": headline, "importance": importance, "market_impact": impact, "source": source}


def test_footer_always_present() -> None:
    from app.domains.news.reports import render_telegram_digest

    md = render_telegram_digest({"date": "2026-07-18", "products": []})
    assert md.endswith("🤖 Powered by IMEX AI")
    assert "📰 *Обзор рынка — 2026-07-18*" in md


def test_never_exceeds_limit_even_with_many_items() -> None:
    from app.domains.news.reports import TELEGRAM_DIGEST_LIMIT, render_telegram_digest

    snapshot = {
        "date": "2026-07-18",
        "i18n": {"summary": {"ru": "Очень длинное резюме. " * 60}},
        "top_news": {
            "count": 40,
            "top": [_news(f"Заголовок новости номер {i} про завод и остановку", source=f"src{i}") for i in range(40)],
            "themes": {"shutdowns": ["A", "B"], "projects": ["C", "D"], "energy": ["E"], "logistics": ["F"]},
        },
        "products": [
            {"code": "HDPE", "price": 12000000, "currency": "UZS", "delta": -500000},
            {"code": "PP", "price": 11000000, "currency": "UZS", "delta": 300000},
        ],
    }
    md = render_telegram_digest(snapshot)
    assert len(md) <= TELEGRAM_DIGEST_LIMIT
    assert md.endswith("🤖 Powered by IMEX AI")  # footer survives trimming


def test_includes_top_news_with_markers() -> None:
    from app.domains.news.reports import render_telegram_digest

    snapshot = {
        "date": "2026-07-18",
        "top_news": {
            "count": 2,
            "top": [
                _news("Shurtan останавливает PP-линию", "high", "negative", "PetroTG"),
                _news("Новый завод метанола", "medium", "positive", "GovUZ"),
            ],
            "themes": {},
        },
        "products": [],
    }
    md = render_telegram_digest(snapshot)
    assert "*Главные новости:*" in md
    assert "Shurtan останавливает PP-линию" in md
    assert "🔴📉" in md          # high + negative
    assert "🟡📈" in md          # medium + positive
    assert "PetroTG" in md


def test_prefers_i18n_summary_over_rule_based() -> None:
    from app.domains.news.reports import render_telegram_digest

    snapshot = {
        "date": "2026-07-18",
        "i18n": {"summary": {"ru": "Рынок стабилен, цены без изменений."}},
        "products": [{"code": "PP", "price": 1, "currency": "UZS", "delta": 0}],
        "top_news": {"count": 0, "top": [], "themes": {}},
    }
    md = render_telegram_digest(snapshot)
    assert "Рынок стабилен, цены без изменений." in md


def test_empty_snapshot_is_valid_short_message() -> None:
    from app.domains.news.reports import TELEGRAM_DIGEST_LIMIT, render_telegram_digest

    md = render_telegram_digest({"date": "2026-07-18", "products": []})
    assert len(md) <= TELEGRAM_DIGEST_LIMIT
    assert "📰 *Обзор рынка" in md
    assert md.endswith("🤖 Powered by IMEX AI")


def test_price_movers_line_when_room() -> None:
    from app.domains.news.reports import render_telegram_digest

    snapshot = {
        "date": "2026-07-18",
        "top_news": {"count": 0, "top": [], "themes": {}},
        "products": [
            {"code": "HDPE", "price": 12000000, "currency": "UZS", "delta": -500000},
            {"code": "PP", "price": 11000000, "currency": "UZS", "delta": 300000},
        ],
    }
    md = render_telegram_digest(snapshot)
    assert "💱" in md
    assert "HDPE" in md  # biggest absolute mover surfaces
