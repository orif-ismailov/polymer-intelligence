"""
Tests for the Phase 7b news path:

- news_service.create_news_signal_from_article (NewsArticle → kind='news' Signal + ai)
- parse_news_item task routing (relevant → news signal; irrelevant → no signal)
- run_source_fetch_isolated routes content_kind='news' sources to parse_news_item

LLM/DB/Celery are mocked — no network, no Postgres, no broker.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


def _article(**over: Any) -> Any:
    from parsing.news_schemas import NewsArticle

    base: dict[str, Any] = dict(
        is_relevant=True,
        headline="Shurtan GCC lifts PP offers",
        category="polypropylene",
        tags=["market_prices"],
        country="Uzbekistan",
        related_products=["PP"],
        companies=["Shurtan GCC"],
        importance="high",
        market_impact="positive",
        summary="Domestic PP quotes firm up; buyers should expect higher asks.",
        confidence=0.9,
    )
    base.update(over)
    return NewsArticle(**base)


def _raw_item(content: str = "Shurtan raised PP prices today.") -> MagicMock:
    r = MagicMock()
    r.id = 501
    r.source_id = 9
    r.content = content
    r.parse_status = "pending"
    r.event_at = None
    return r


# ── Service: NewsArticle → Signal ─────────────────────────────────────────────


class TestCreateNewsSignal:
    def test_maps_article_to_news_signal(self) -> None:
        from app.models.enums import SignalKind
        from app.services.news_service import create_news_signal_from_article

        with patch("app.services.news_service.match_product", return_value=7):
            sig = create_news_signal_from_article(
                MagicMock(), _raw_item(), _article(), {"model": "haiku", "prompt_version": "v1"},
                needs_review=False,
            )

        assert sig.kind == SignalKind.news
        assert sig.grade_text == "Shurtan GCC lifts PP offers"   # headline in feed column
        assert sig.region == "Uzbekistan"
        assert sig.product_id == 7                               # resolved from related_products
        news = sig.ai["news"]
        assert news["category"] == "polypropylene"
        assert news["importance"] == "high"
        assert news["market_impact"] == "positive"
        assert news["companies"] == ["Shurtan GCC"]
        assert sig.ai["needs_review"] is False

    def test_stores_analysis_recommendation_and_i18n(self) -> None:
        """Phase 8b/8f: the news block carries analysis/recommendation/language + ru/uz/en."""
        from app.services.news_service import create_news_signal_from_article
        from parsing.news_schemas import NewsI18n, NewsLocalized

        article = _article(
            analysis="What happened: prices rose. Why it matters: tighter supply.",
            recommendation="Monitor PP prices; expect firmer asks.",
            countries=["Uzbekistan"],
            language="en",
            i18n=NewsI18n(
                ru=NewsLocalized(headline="Shurtan поднял цены на PP", recommendation="Следите за ценами PP."),
                uz=NewsLocalized(headline="Shurtan PP narxini oshirdi"),
            ),
        )
        with patch("app.services.news_service.match_product", return_value=None):
            sig = create_news_signal_from_article(
                MagicMock(), _raw_item(), article, {"model": "haiku", "prompt_version": "v2"},
                needs_review=False,
            )
        news = sig.ai["news"]
        assert news["analysis"].startswith("What happened")
        assert news["recommendation"] == "Monitor PP prices; expect firmer asks."
        assert news["countries"] == ["Uzbekistan"]
        assert news["language"] == "en"
        assert news["i18n"]["ru"]["headline"] == "Shurtan поднял цены на PP"
        assert news["i18n"]["uz"]["headline"] == "Shurtan PP narxini oshirdi"
        assert "recommendation" not in news["i18n"]["uz"]  # exclude_none drops empty fields


# ── Task routing ──────────────────────────────────────────────────────────────


def _patch_session(mock_get_session: MagicMock, raw_item: MagicMock) -> MagicMock:
    session = MagicMock()
    mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
    mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
    session.get.return_value = raw_item
    return session


class TestParseNewsItem:
    def test_relevant_creates_news_signal(self) -> None:
        from app.tasks.parse import parse_news_item

        raw_item = _raw_item()
        with (
            patch("app.tasks.parse.get_session") as mock_gs,
            patch("app.tasks.parse.check_and_reserve_tokens"),
            patch("app.tasks.parse.record_actual_tokens"),
            patch("app.tasks.parse.news_extract_signal", return_value=(_article(), {"parser": "news_extract_tools", "model": "haiku"})),
            patch("app.tasks.parse.write_parse_run"),
            patch("app.services.news_service.create_news_signal_from_article") as mock_create,
        ):
            _patch_session(mock_gs, raw_item)
            mock_create.return_value = MagicMock(id=1)
            result = parse_news_item(501)

        assert result["status"] == "parsed"
        mock_create.assert_called_once()
        assert raw_item.parse_status == "parsed"

    def test_budget_exceeded_defers_not_drops(self) -> None:
        """Phase 8g fix: budget exhaustion → 'budget_deferred' (retryable), not 'irrelevant'."""
        from app.tasks.parse import parse_news_item
        from parsing.budget import BudgetExceeded

        raw_item = _raw_item()
        with (
            patch("app.tasks.parse.get_session") as mock_gs,
            patch("app.tasks.parse.check_and_reserve_tokens", side_effect=BudgetExceeded("no budget")),
            patch("app.tasks.parse.write_parse_run"),
            patch("app.services.news_service.create_news_signal_from_article") as mock_create,
        ):
            _patch_session(mock_gs, raw_item)
            result = parse_news_item(501)

        assert result["status"] == "budget_deferred"
        assert raw_item.parse_status == "budget_deferred"
        mock_create.assert_not_called()

    def test_irrelevant_makes_no_signal(self) -> None:
        from app.tasks.parse import parse_news_item

        raw_item = _raw_item()
        with (
            patch("app.tasks.parse.get_session") as mock_gs,
            patch("app.tasks.parse.check_and_reserve_tokens"),
            patch("app.tasks.parse.record_actual_tokens"),
            patch("app.tasks.parse.news_extract_signal", return_value=(_article(is_relevant=False), {})),
            patch("app.tasks.parse.write_parse_run"),
            patch("app.services.news_service.create_news_signal_from_article") as mock_create,
        ):
            session = _patch_session(mock_gs, raw_item)
            result = parse_news_item(501)

        assert result["status"] == "irrelevant"
        assert raw_item.parse_status == "irrelevant"
        mock_create.assert_not_called()
        session.add.assert_not_called()


# ── Source routing ────────────────────────────────────────────────────────────


class TestNewsSourceRouting:
    def test_news_source_routes_to_parse_news_item(self) -> None:
        from app.tasks import ingest

        source = MagicMock(id=9)
        source.config = {"content_kind": "news"}

        with (
            patch("app.tasks.ingest._run_fetch_for_source", return_value=[MagicMock()]),
            patch("app.tasks.ingest.save_raw_items", return_value=(1, [77])),
            patch("app.tasks.ingest.record_fetch_success"),
            patch("app.tasks.ingest._enqueue_parse_tasks") as mock_enqueue,
        ):
            ingest.run_source_fetch_isolated(MagicMock(), source, MagicMock(), parse_task_name="parse_telegram_item")

        mock_enqueue.assert_called_once_with([77], "parse_news_item")
