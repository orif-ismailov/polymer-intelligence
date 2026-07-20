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
        # default query params forwarded (filters all None, no scope/sort/lang)
        assert mock_list.call_args.kwargs == {
            "limit": 30, "days": 7, "q": None, "scope": None, "category": None,
            "country": None, "company": None, "product": None, "importance": None,
            "source_id": None, "sort": None, "lang": None,
        }

    def test_list_articles_forwards_filters(self) -> None:
        """Search/scope/sort/facet query params reach the service verbatim."""
        with patch("app.services.news_service.list_news_articles", return_value=[]) as mock_list:
            resp = _client().get(
                "/api/v1/webapp/news/articles",
                params={
                    "q": "shurtan", "scope": "producers", "category": "plant_shutdown",
                    "country": "UZ", "company": "Shurtan", "product": "PP",
                    "importance": "high", "source_id": 5, "sort": "newest",
                    "lang": "uz", "limit": 10, "days": 14,
                },
            )
        assert resp.status_code == 200, resp.text
        assert mock_list.call_args.kwargs == {
            "limit": 10, "days": 14, "q": "shurtan", "scope": "producers",
            "category": "plant_shutdown", "country": "UZ", "company": "Shurtan",
            "product": "PP", "importance": "high", "source_id": 5, "sort": "newest",
            "lang": "uz",
        }

    def test_scope_all_becomes_no_filter(self) -> None:
        """scope=all is the unfiltered default — the service receives scope=None."""
        with patch("app.services.news_service.list_news_articles", return_value=[]) as mock_list:
            resp = _client().get("/api/v1/webapp/news/articles", params={"scope": "all"})
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs["scope"] is None

    def test_invalid_scope_rejected(self) -> None:
        resp = _client().get("/api/v1/webapp/news/articles", params={"scope": "mars"})
        assert resp.status_code == 422

    def test_filters_endpoint_returns_facets(self) -> None:
        options = {
            "categories": [{"value": "plant_shutdown", "count": 4}],
            "countries": [{"value": "UZ", "count": 9}],
            "companies": [{"value": "Shurtan GCC", "count": 3}],
            "products": [{"value": "PP", "count": 6}],
        }
        with patch("app.services.news_service.list_news_filter_options", return_value=options) as mock_opts:
            resp = _client().get("/api/v1/webapp/news/articles/filters")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["categories"][0] == {"value": "plant_shutdown", "count": 4}
        assert body["products"][0]["value"] == "PP"
        assert mock_opts.call_args.kwargs == {"days": 30}

    def test_filters_route_not_swallowed_by_article_id(self) -> None:
        """/articles/filters resolves to the facets route, not GET /articles/{id}."""
        with patch("app.services.news_service.list_news_filter_options", return_value={}) as mock_opts, \
             patch("app.services.news_service.get_news_article") as mock_get:
            resp = _client().get("/api/v1/webapp/news/articles/filters")
        assert resp.status_code == 200
        mock_opts.assert_called_once()
        mock_get.assert_not_called()

    def test_articles_route_not_swallowed_by_report_id(self) -> None:
        """The /articles path resolves to list_articles, not GET /{report_id}."""
        with patch("app.services.news_service.list_news_articles", return_value=[]) as mock_list, \
             patch("app.services.report_service.get_published") as mock_report:
            resp = _client().get("/api/v1/webapp/news/articles")
        assert resp.status_code == 200
        mock_list.assert_called_once()
        mock_report.assert_not_called()

    def test_list_articles_passes_merged_sources(self) -> None:
        """Phase 7f: a cross-source-merged card round-trips its sources + merged_count."""
        merged = {
            **_CARD,
            "merged_count": 3,
            "sources": [
                {"id": 40, "name": "TG-A", "published_at": "2026-07-18T07:00:00+00:00"},
                {"id": 41, "name": "TG-B", "published_at": "2026-07-18T07:30:00+00:00"},
                {"id": 42, "name": "PetroTG", "published_at": "2026-07-18T08:00:00+00:00"},
            ],
        }
        with patch("app.services.news_service.list_news_articles", return_value=[merged]):
            resp = _client().get("/api/v1/webapp/news/articles")
        assert resp.status_code == 200, resp.text
        body = resp.json()[0]
        assert body["merged_count"] == 3
        assert [s["name"] for s in body["sources"]] == ["TG-A", "TG-B", "PetroTG"]

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


class TestNewsFilterSql:
    """The WHERE-clause builder keeps every user value in bound params (injection-safe)."""

    def test_no_filters_is_empty(self) -> None:
        from app.services.news_service import _news_filter_sql  # noqa: PLC0415

        clauses, params = _news_filter_sql(
            q=None, scope=None, category=None, country=None,
            company=None, product=None, importance=None, source_id=None,
        )
        assert clauses == []
        assert params == {}

    def test_search_binds_wildcarded_param(self) -> None:
        from app.services.news_service import _news_filter_sql  # noqa: PLC0415

        clauses, params = _news_filter_sql(
            q="shurtan", scope=None, category=None, country=None,
            company=None, product=None, importance=None, source_id=None,
        )
        assert params == {"q": "%shurtan%"}
        assert all(":q" in c or "ILIKE" in c for c in clauses)
        assert "shurtan" not in " ".join(clauses)  # value never inlined into SQL

    def test_scope_producers_uses_static_category_list(self) -> None:
        from app.services.news_service import _news_filter_sql  # noqa: PLC0415

        clauses, params = _news_filter_sql(
            q=None, scope="producers", category=None, country=None,
            company=None, product=None, importance=None, source_id=None,
        )
        assert params == {}  # producer categories are static constants, not user input
        assert "plant_shutdown" in clauses[0]

    def test_all_facets_bind(self) -> None:
        from app.services.news_service import _news_filter_sql  # noqa: PLC0415

        _, params = _news_filter_sql(
            q=None, scope="global", category="oil", country="UZ",
            company="SIBUR", product="PP", importance="high", source_id=7,
        )
        assert params == {
            "category": "oil", "country": "UZ", "company": "%SIBUR%",
            "product": "%PP%", "importance": "high", "source_id": 7,
        }


class TestSortCards:
    def _cards(self) -> list[dict[str, object]]:
        return [
            {"importance": "low", "published_at": "2026-07-20", "category": "oil",
             "country": "RU", "companies": ["Zeta"], "related_products": ["PVC"]},
            {"importance": "high", "published_at": "2026-07-18", "category": "abs",
             "country": "UZ", "companies": ["Alpha"], "related_products": ["HDPE"]},
        ]

    def test_default_keeps_sql_order(self) -> None:
        from app.services.news_service import _sort_cards  # noqa: PLC0415

        cards = self._cards()
        assert _sort_cards(cards, None) == cards
        assert _sort_cards(cards, "importance") == cards

    def test_newest_orders_by_published_desc(self) -> None:
        from app.services.news_service import _sort_cards  # noqa: PLC0415

        out = _sort_cards(self._cards(), "newest")
        assert [c["published_at"] for c in out] == ["2026-07-20", "2026-07-18"]

    def test_category_sorts_alphabetically(self) -> None:
        from app.services.news_service import _sort_cards  # noqa: PLC0415

        out = _sort_cards(self._cards(), "category")
        assert [c["category"] for c in out] == ["abs", "oil"]

    def test_company_sorts_by_first_company(self) -> None:
        from app.services.news_service import _sort_cards  # noqa: PLC0415

        out = _sort_cards(self._cards(), "company")
        assert [c["companies"] for c in out] == [["Alpha"], ["Zeta"]]


class TestLocalize:
    def _card(self) -> dict[str, object]:
        return {
            "headline": "Shurtan halts PP line", "summary": "EN summary",
            "analysis": "EN analysis", "recommendation": "EN rec",
            "i18n": {
                "uz": {"headline": "Shurtan PP liniyasini to'xtatdi", "summary": "UZ xulosa",
                       "analysis": "UZ tahlil", "recommendation": "UZ tavsiya"},
                "ru": {"headline": "Shurtan остановил PP"},  # partial translation
            },
        }

    def test_localizes_all_present_fields(self) -> None:
        from app.services.news_service import _localize  # noqa: PLC0415

        out = _localize(self._card(), "uz")
        assert out["headline"] == "Shurtan PP liniyasini to'xtatdi"
        assert out["analysis"] == "UZ tahlil"
        assert out["recommendation"] == "UZ tavsiya"

    def test_missing_fields_fall_back_to_canonical(self) -> None:
        from app.services.news_service import _localize  # noqa: PLC0415

        out = _localize(self._card(), "ru")
        assert out["headline"] == "Shurtan остановил PP"
        assert out["summary"] == "EN summary"  # ru variant had no summary → canonical

    def test_no_lang_or_missing_lang_is_noop(self) -> None:
        from app.services.news_service import _localize  # noqa: PLC0415

        assert _localize(self._card(), None)["headline"] == "Shurtan halts PP line"
        assert _localize(self._card(), "fa")["headline"] == "Shurtan halts PP line"
