"""
Phase 3 news-engine tests: deterministic report rendering + reports/news API.

The render/summary helpers are pure (no DB/LLM) and tested directly. The API tests
are fully mocked (MagicMock db + dependency overrides), mirroring the other API tests.
"""

from __future__ import annotations

import datetime
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Pure rendering / summary ────────────────────────────────────────────────────

class TestRender:
    def _snapshot(self) -> dict[str, Any]:
        return {
            "date": "2026-06-28",
            "products": [
                {"code": "HDPE", "price": 1095.0, "currency": "USD", "unit": "MT", "delta": 15.0, "observed_on": "2026-06-28"},
                {"code": "PP", "price": 1120.0, "currency": "USD", "unit": "MT", "delta": -10.0, "observed_on": "2026-06-28"},
            ],
            "buy_requests_7d": 14,
            "sell_offers_7d": 8,
        }

    def test_rule_based_summary_directional(self):
        from app.domains.news.reports import _rule_based_summary

        up = {"products": [{"delta": 5.0}, {"delta": 2.0}, {"delta": -1.0}]}
        down = {"products": [{"delta": -5.0}, {"delta": -2.0}, {"delta": 1.0}]}
        assert "выросли" in _rule_based_summary(up)
        assert "снизились" in _rule_based_summary(down)
        assert "Недостаточно" in _rule_based_summary({"products": []})

    def test_rule_based_summary_weaves_local_market_and_sections(self):
        """Fallback (LLM down) still reports UZEX activity + which sections carry news."""
        from app.domains.news.reports import _rule_based_summary

        snap = {
            "products": [{"delta": 5.0}, {"delta": 2.0}],
            "local_market": {"exchange": {"deals": 42, "quotes": 376, "offers": 7}},
            "news_explored_count": 63,
            "sections": {
                "uzbekistan": [{"headline": "x"}], "producers": [], "global": [{"headline": "y"}],
            },
        }
        out = _rule_based_summary(snap)
        assert "выросли" in out
        assert "UZEX" in out and "сделок — 42" in out
        assert "Обработано 63" in out
        assert "Узбекистан" in out and "мировой рынок" in out
        assert "производители" not in out  # empty producers section not listed

    def test_report_prompt_v6_ships(self):
        from app.domains.news.reports import _load_prompt

        prompt = _load_prompt("v6")
        assert prompt and "summary" in prompt and "briefs" in prompt

    def test_render_markdown_contains_products_and_summary(self):
        from app.domains.news.reports import render_markdown

        md = render_markdown(self._snapshot(), "Тестовое резюме.")
        assert "Ежедневный обзор рынка" in md
        assert "HDPE" in md and "PP" in md
        assert "(+15)" in md  # positive delta sign
        assert "(-10)" in md
        assert "Тестовое резюме." in md
        assert "запросы — 14" in md

    def test_render_markdown_shows_explored_count_above_summary(self):
        from app.domains.news.reports import render_markdown

        snap = {**self._snapshot(), "news_explored_count": 63}
        md = render_markdown(snap, "Резюме.")
        assert "🤖 *AI Summary*" in md
        assert "обработано новостей: 63" in md
        # the count line sits above the summary paragraph
        assert md.index("обработано новостей: 63") < md.index("Резюме.")

    def test_render_markdown_omits_count_line_when_absent(self):
        from app.domains.news.reports import render_markdown

        md = render_markdown(self._snapshot(), "Резюме.")  # no news_explored_count
        assert "обработано новостей" not in md

    def _card(self, **over: Any) -> dict[str, Any]:
        base = {
            "id": 1, "headline": "Shurtan останавливает PP-линию", "importance": "high",
            "market_impact": "negative", "summary": "Ремонт сократит выпуск PP.",
            "recommendation": "Следите за ценами PP.", "related_products": ["PP"],
            "source_name": "UzPetro", "merged_count": 2,
        }
        base.update(over)
        return base

    def test_render_markdown_three_sections(self):
        from app.domains.news.reports import render_markdown

        snap = {
            **self._snapshot(),
            "sections": {
                "uzbekistan": [self._card()],
                "global": [self._card(headline="SIBUR expands ethylene", importance="medium")],
                "producers": [self._card(headline="Shurtan announcement")],
            },
        }
        md = render_markdown(snap, "Резюме.")
        assert "🇺🇿 *Узбекистан*" in md
        assert "🌍 *Мировой рынок*" in md
        assert "🏭 *Производители*" in md
        assert "Shurtan останавливает PP-линию" in md
        assert "[PP]" in md  # products rendered inline (compact)
        assert "(+1)" in md  # merged_count=2 → +N suffix
        assert "Ремонт сократит выпуск PP." in md  # short one-line summary IS rendered
        # but the verbose 3-sentence recommendation is NOT (that's on the News card)
        assert "Следите за ценами PP." not in md
        # legacy excerpt blocks are suppressed when sections are present
        assert "Мировая нефтехимия" not in md

    def test_render_sections_dedupes_across_sections(self):
        from app.domains.news.reports import _render_sections

        # same story in two sections → rendered once (first section that claims it)
        dup = self._card(headline="Салават остановлен")
        out = "\n".join(_render_sections({
            "uzbekistan": [dup], "producers": [dup], "global": [],
        }))
        assert out.count("Салават остановлен") == 1

    def test_render_telegram_digest_sections(self):
        from app.domains.news.reports import render_telegram_digest

        snap = {
            "date": "2026-07-21",
            "sections": {"uzbekistan": [self._card()], "global": [], "producers": []},
        }
        out = render_telegram_digest(snap)
        assert "🇺🇿 *Узбекистан*" in out
        assert "Shurtan останавливает PP-линию" in out
        assert "Powered by IMEX AI" in out


class TestLocalMarket:
    def test_render_fx_and_exchange(self):
        from app.domains.news.reports import _render_local_market

        lm = {
            "fx": [
                {"ccy": "USD", "rate": 11960.09},
                {"ccy": "EUR", "rate": 13670.38},
                {"ccy": "RUB", "rate": 152.53},
            ],
            "exchange": {"deals": 42, "quotes": 376, "offers": 7, "top_products": []},
            "window_days": 7,
        }
        out = "\n".join(_render_local_market(lm))
        assert "Локальный рынок" in out
        assert "USD 11,960" in out and "EUR 13,670" in out
        assert "сделок — 42" in out and "котировок — 376" in out
        # noisy UZEX product breakdown is intentionally NOT rendered (fertilizer/off-domain)
        assert "Карбамид" not in out

    def test_render_empty_when_no_data(self):
        from app.domains.news.reports import _render_local_market

        assert _render_local_market(
            {"fx": [], "exchange": {"deals": 0, "quotes": 0, "offers": 0, "top_products": []}}
        ) == []

    def test_render_fx_only(self):
        from app.domains.news.reports import _render_local_market

        out = "\n".join(_render_local_market({"fx": [{"ccy": "USD", "rate": 12000.0}], "exchange": {}}))
        assert "USD 12,000" in out
        assert "Биржа UZEX" not in out  # no exchange activity → that line is skipped


class TestSectionBriefs:
    def test_render_briefs_paragraph_per_section(self):
        from app.domains.news.reports import _render_section_briefs

        sections = {"uzbekistan": [{"headline": "x"}], "producers": [], "global": [{"headline": "y"}]}
        briefs = {
            "uzbekistan": "Узбекистан наращивает нефтехимические мощности.",
            "producers": "",  # empty brief → skipped
            "global": "Цены на смолы растут по всем маркам.",
        }
        out = "\n".join(_render_section_briefs(sections, briefs))
        assert "🇺🇿 *Узбекистан*" in out and "Узбекистан наращивает" in out
        assert "🌍 *Мировой рынок*" in out and "Цены на смолы растут" in out
        assert "🏭" not in out  # producers: no news + empty brief → not shown

    def test_render_markdown_prefers_briefs_over_item_list(self):
        from app.domains.news.reports import render_markdown

        snap = {
            "date": "2026-07-21", "products": [],
            "sections": {"uzbekistan": [{
                "headline": "Проект полимеров из угля", "summary": "детали проекта",
                "importance": "high", "market_impact": "positive",
                "source_name": "Uz", "related_products": [],
            }]},
            "briefs": {"uzbekistan": "Синтез: Узбекистан развивает производство полимеров.",
                       "producers": "", "global": ""},
        }
        md = render_markdown(snap, "Резюме.")
        assert "Синтез: Узбекистан развивает производство полимеров." in md  # the AI brief
        assert "Проект полимеров из угля" not in md  # per-item headline list NOT used when briefs exist

    def test_render_markdown_falls_back_to_headlines_without_briefs(self):
        from app.domains.news.reports import render_markdown

        snap = {
            "date": "2026-07-21", "products": [],
            "sections": {"uzbekistan": [{
                "headline": "Проект полимеров из угля", "summary": "детали",
                "importance": "high", "market_impact": "positive", "source_name": "Uz",
                "related_products": ["PP"],
            }]},
            # no "briefs" → compact headline fallback
        }
        md = render_markdown(snap, "Резюме.")
        assert "Проект полимеров из угля" in md  # falls back to the compact headline list


class TestSessionMeta:
    def test_morning_and_evening_map_to_kind_and_title(self):
        from app.domains.news.reports import _session_meta
        from app.models.enums import ReportKind

        assert _session_meta("morning", "2026-07-21") == (
            ReportKind.morning, "Утренний обзор рынка — 2026-07-21")
        assert _session_meta("evening", "2026-07-21") == (
            ReportKind.evening, "Вечерний обзор рынка — 2026-07-21")

    def test_unknown_session_defaults_to_morning(self):
        from app.domains.news.reports import _session_meta
        from app.models.enums import ReportKind

        kind, title = _session_meta("weird", "2026-07-21")
        assert kind is ReportKind.morning
        assert title.startswith("Утренний")


class TestBreakingAlert:
    def test_renders_breaking_story(self):
        from app.domains.news.reports import render_breaking_alert

        card = {
            "headline": "Взрыв на заводе SIBUR", "market_impact": "negative",
            "summary": "Пожар остановил производство этилена.",
            "recommendation": "Ожидайте рост цен на этилен.",
            "source_name": "OilTG", "merged_count": 3,
        }
        out = render_breaking_alert(card)
        assert "СРОЧНО" in out
        assert "🔴📉" in out
        assert "Взрыв на заводе SIBUR" in out
        assert "💡 Ожидайте рост цен на этилен." in out
        assert "(+2)" in out  # merged_count=3
        assert "Powered by IMEX AI" in out


# ── API (mocked) ─────────────────────────────────────────────────────────────────

def _mock_report(id: int = 5, status: str = "published") -> MagicMock:
    from app.models.enums import ReportKind, ReportStatus  # noqa: PLC0415

    r = MagicMock()
    r.id = id
    r.title = "Обзор рынка — 2026-06-28"
    r.kind = ReportKind.morning
    r.status = ReportStatus(status)
    r.content_md = "📊 *Ежедневный обзор рынка*"
    r.generated_by = "rule_based"
    r.data_snapshot = {"products": []}
    r.period_start = datetime.date(2026, 6, 28)
    r.period_end = datetime.date(2026, 6, 28)
    r.published_at = datetime.datetime(2026, 6, 28, 8, 0, tzinfo=datetime.UTC)
    r.created_at = datetime.datetime(2026, 6, 28, 7, 0, tzinfo=datetime.UTC)
    return r


@pytest.fixture
def news_client() -> Generator[TestClient, None, None]:
    from app.api.deps import get_current_client  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    def _db() -> Generator[Any, None, None]:
        yield MagicMock()

    application = create_app()
    application.dependency_overrides[get_db] = _db
    application.dependency_overrides[get_current_client] = lambda: MagicMock(id=1, telegram_user_id=5)
    with patch("app.api.health._check_redis", return_value="ok"), TestClient(application) as tc:
        yield tc


class TestNewsApi:
    def test_list_published_200(self, news_client: TestClient):
        with patch("app.domains.news.api_webapp.report_service") as svc:
            svc.list_published.return_value = [_mock_report()]
            resp = news_client.get("/api/v1/webapp/news")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["title"].startswith("Обзор")

    def test_detail_404_when_not_published(self, news_client: TestClient):
        with patch("app.domains.news.api_webapp.report_service") as svc:
            svc.get_published.return_value = None
            resp = news_client.get("/api/v1/webapp/news/999")
        assert resp.status_code == 404, resp.text

    def test_news_requires_initdata(self):
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        def _db() -> Generator[Any, None, None]:
            yield MagicMock()

        application = create_app()
        application.dependency_overrides[get_db] = _db
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(
            application, raise_server_exceptions=False
        ) as tc:
            resp = tc.get("/api/v1/webapp/news")
        assert resp.status_code == 401, resp.text


class TestReportsAdminApi:
    def test_list_requires_staff(self):
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        def _db() -> Generator[Any, None, None]:
            yield MagicMock()

        application = create_app()
        application.dependency_overrides[get_db] = _db
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(
            application, raise_server_exceptions=False
        ) as tc:
            resp = tc.get("/api/v1/admin/reports")
        assert resp.status_code == 401, resp.text

    def test_publish_200(self):
        from app.api.deps import require_analyst_or_admin  # noqa: PLC0415
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        def _db() -> Generator[Any, None, None]:
            yield MagicMock()

        application = create_app()
        application.dependency_overrides[get_db] = _db
        application.dependency_overrides[require_analyst_or_admin] = lambda: MagicMock(id=3)
        with patch("app.api.health._check_redis", return_value="ok"), patch(
            "app.domains.news.api_admin.report_service"
        ) as svc, TestClient(application) as tc:
            svc.get_report.return_value = _mock_report(status="approved")
            svc.publish_report.return_value = _mock_report(status="published")
            resp = tc.post("/api/v1/admin/reports/5/publish")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "published"
