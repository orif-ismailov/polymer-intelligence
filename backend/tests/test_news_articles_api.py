"""
Tests for the Phase 7e webapp news-article surface.

- /webapp/news/articles[/{id}] must resolve BEFORE /webapp/news/{report_id}
  (the string "articles" must not be swallowed by the int report-id route).
- news_service._article_card maps a signal's ai.news JSONB into a card dict.

DB + auth are mocked — no Postgres, no initData.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from app.api.deps import get_current_client  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    def _override_db() -> Generator[Any, None, None]:
        yield MagicMock()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_client] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=True)


_CARD = {
    "id": 42,
    "headline": "Shurtan останавливает PP-линию",
    "category": "plant_shutdown",
    "importance": "high",
    "market_impact": "negative",
    "summary": "Плановый ремонт сократит выпуск PP.",
    "country": "UZ",
    "companies": ["Shurtan GCC"],
    "related_products": ["PP"],
    "source_name": "PetroTG",
    "published_at": "2026-07-18T08:00:00+00:00",
    "image_url": None,
}


class TestNewsArticlesApi:
    def test_list_articles_returns_cards(self) -> None:
        with patch("app.services.news_service.list_news_articles", return_value=[_CARD]) as mock_list:
            resp = _client().get("/api/v1/webapp/news/articles")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body[0]["id"] == 42
        assert body[0]["headline"].startswith("Shurtan")
        assert body[0]["related_products"] == ["PP"]
        # default query params forwarded
        assert mock_list.call_args.kwargs == {"limit": 30, "days": 7}

    def test_articles_route_not_swallowed_by_report_id(self) -> None:
        """The /articles path resolves to list_articles, not GET /{report_id}."""
        with patch("app.services.news_service.list_news_articles", return_value=[]) as mock_list, \
             patch("app.services.report_service.get_published") as mock_report:
            resp = _client().get("/api/v1/webapp/news/articles")
        assert resp.status_code == 200
        mock_list.assert_called_once()
        mock_report.assert_not_called()

    def test_get_article_detail(self) -> None:
        detail = {**_CARD, "body": "Полный текст новости…", "source_url": "https://t.me/petro/1"}
        with patch("app.services.news_service.get_news_article", return_value=detail):
            resp = _client().get("/api/v1/webapp/news/articles/42")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_url"] == "https://t.me/petro/1"
        assert body["body"].startswith("Полный текст")

    def test_get_article_404(self) -> None:
        with patch("app.services.news_service.get_news_article", return_value=None):
            resp = _client().get("/api/v1/webapp/news/articles/999")
        assert resp.status_code == 404


class TestArticleCardMapping:
    def test_article_card_reads_ai_news_block(self) -> None:
        import datetime  # noqa: PLC0415

        from app.services.news_service import _article_card  # noqa: PLC0415

        row = {
            "id": 7,
            "event_at": datetime.datetime(2026, 7, 18, 6, 0, tzinfo=datetime.UTC),
            "country": "RU",
            "source_name": "OilTG",
            "ai": {
                "news": {
                    "headline": "Brent растёт",
                    "category": "oil",
                    "importance": "medium",
                    "market_impact": "positive",
                    "summary": "Нефть дорожает.",
                    "companies": ["OPEC"],
                    "related_products": [],
                    "country": None,  # falls back to the source country
                }
            },
        }
        card = _article_card(row)
        assert card["id"] == 7
        assert card["headline"] == "Brent растёт"
        assert card["country"] == "RU"  # ai.news.country None → source country
        assert card["companies"] == ["OPEC"]
        assert card["published_at"] == "2026-07-18T06:00:00+00:00"
        assert card["image_url"] is None
