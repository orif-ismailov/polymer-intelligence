"""
AI Daily Market Digest tests (report engine v2).

- render_markdown: renders the new 24h sections (UZEX, buyer requests, offers, news
  UZ/world, forecast) and stays backward-compatible with pre-digest snapshots.
- _ai_digest: parses strict-JSON multi-language output; returns None on garbage /
  missing Russian summary (→ rule-based fallback in generate_report).
- generate_report: stores i18n in the snapshot when the LLM succeeds; degrades to
  rule_based with no forecast when it fails.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


def _digest_snapshot() -> dict[str, Any]:
    return {
        "date": "2026-07-15",
        "products": [
            {"code": "HDPE", "price": 1095.0, "currency": "USD", "unit": "MT", "delta": 15.0, "observed_on": "2026-07-15"},
        ],
        "buy_requests_7d": 14,
        "sell_offers_7d": 8,
        "tenders_24h": {
            "count": 3,
            "items": [
                {"code": "PP", "kind": "sell_offer", "volume": 500.0, "volume_unit": "MT", "price": 1145.0, "currency": "USD"},
            ],
        },
        "new_requests_24h": {
            "count": 2,
            "items": [{"label": "LDPE", "volume": 100.0, "volume_unit": "MT"}],
        },
        "new_offers_24h": {"count": 4},
        "news_uz": [{"source": "UzDaily", "country": "UZ", "excerpt": "Запущено новое производство ПП в Ташкенте."}],
        "news_world": [{"source": "PolymerUpdate", "country": None, "excerpt": "Sinopec announced a cracker turnaround."}],
    }


class TestRenderDigest:
    def test_renders_all_sections(self) -> None:
        from app.domains.news.reports import render_markdown  # noqa: PLC0415

        md = render_markdown(_digest_snapshot(), "Резюме.", "Прогноз: рост вероятен.")
        assert "Биржа и тендеры (24ч)" in md and "новых позиций: 3" in md
        assert "PP · 500 MT · 1,145 USD" in md
        assert "Новые заявки покупателей (24ч)*: 2" in md
        assert "LDPE — 100 MT" in md
        assert "Новые предложения на маркете (24ч)*: 4" in md
        assert "Новости Узбекистана" in md and "UzDaily" in md
        assert "Мировая нефтехимия" in md and "PolymerUpdate" in md
        assert "🔮" in md and "Прогноз: рост вероятен." in md

    def test_backward_compatible_with_old_snapshot(self) -> None:
        """A pre-digest snapshot (no 24h keys) renders without the new sections."""
        from app.domains.news.reports import render_markdown  # noqa: PLC0415

        old = {
            "date": "2026-06-28",
            "products": [{"code": "PP", "price": 1120.0, "currency": "USD", "unit": "MT", "delta": -10.0}],
            "buy_requests_7d": 1,
            "sell_offers_7d": 0,
        }
        md = render_markdown(old, "Резюме.")
        assert "PP" in md and "Резюме." in md
        assert "Биржа и тендеры" not in md
        assert "🔮" not in md  # no forecast argument → no forecast section

    def test_empty_sections_are_skipped(self) -> None:
        from app.domains.news.reports import render_markdown  # noqa: PLC0415

        snap = _digest_snapshot()
        snap["tenders_24h"] = {"count": 0, "items": []}
        snap["new_requests_24h"] = {"count": 0, "items": []}
        snap["new_offers_24h"] = {"count": 0}
        snap["news_uz"] = []
        snap["news_world"] = []
        md = render_markdown(snap, "Резюме.")
        assert "Биржа и тендеры" not in md
        assert "Новые заявки" not in md
        assert "Новости Узбекистана" not in md


class TestAiDigest:
    def _resp(self, text: str) -> MagicMock:
        block = MagicMock()
        block.type = "text"
        block.text = text
        resp = MagicMock()
        resp.content = [block]
        return resp

    def test_parses_strict_json_all_platform_languages(self) -> None:
        from app.core.languages import SUPPORTED_LANGUAGES  # noqa: PLC0415
        from app.domains.news import reports as report_service  # noqa: PLC0415

        payload = (
            '{"summary": {"ru": "Рынок стабилен.", "en": "Market is stable.", "tr": "Piyasa istikrarlı.",'
            ' "uz": "Bozor barqaror.", "fa": "بازار پایدار است.", "zh": "市场稳定。"},'
            ' "forecast": {"ru": "Рост вероятен.", "en": "Growth likely.", "tr": "Büyüme muhtemel.",'
            ' "uz": "O\'sish kutilmoqda.", "fa": "رشد محتمل است.", "zh": "可能上涨。"}}'
        )
        with patch.object(report_service._client, "messages") as mock_msgs:
            mock_msgs.create.return_value = self._resp(payload)
            digest = report_service._ai_digest({"date": "2026-07-15"})
        assert digest is not None
        # Every platform language must be present in both blocks.
        assert set(digest["summary"]) == set(SUPPORTED_LANGUAGES)
        assert set(digest["forecast"]) == set(SUPPORTED_LANGUAGES)
        assert digest["summary"]["zh"] == "市场稳定。"
        assert digest["forecast"]["fa"] == "رشد محتمل است."
        assert digest["forecast"]["tr"] == "Büyüme muhtemel."

    def test_tolerates_markdown_fences(self) -> None:
        from app.core.languages import SUPPORTED_LANGUAGES  # noqa: PLC0415
        from app.domains.news import reports as report_service  # noqa: PLC0415

        payload = '```json\n{"summary": {"ru": "Ок."}, "forecast": {}}\n```'
        with patch.object(report_service._client, "messages") as mock_msgs:
            mock_msgs.create.return_value = self._resp(payload)
            digest = report_service._ai_digest({})
        assert digest is not None
        assert digest["summary"]["ru"] == "Ок."
        assert digest["forecast"] == dict.fromkeys(SUPPORTED_LANGUAGES, "")

    def test_garbage_returns_none(self) -> None:
        from app.domains.news import reports as report_service  # noqa: PLC0415

        with patch.object(report_service._client, "messages") as mock_msgs:
            mock_msgs.create.return_value = self._resp("Сегодня рынок стабилен (не JSON).")
            assert report_service._ai_digest({}) is None

    def test_missing_ru_summary_returns_none(self) -> None:
        from app.domains.news import reports as report_service  # noqa: PLC0415

        with patch.object(report_service._client, "messages") as mock_msgs:
            mock_msgs.create.return_value = self._resp('{"summary": {"en": "only en"}, "forecast": {}}')
            assert report_service._ai_digest({}) is None


class TestGenerateReport:
    def test_llm_success_stores_i18n_and_forecast(self) -> None:
        from app.domains.news import reports as report_service  # noqa: PLC0415

        db = MagicMock()
        digest = {
            "summary": {"ru": "Резюме RU.", "en": "Summary EN.", "uz": "Xulosa UZ."},
            "forecast": {"ru": "Прогноз RU.", "en": "Forecast EN.", "uz": "Prognoz UZ."},
        }
        with (
            patch.object(report_service, "build_snapshot", return_value=_digest_snapshot()),
            patch.object(report_service, "_ai_digest", return_value=digest),
        ):
            report = report_service.generate_report(db, use_llm=True)

        assert report.data_snapshot["i18n"] == digest
        assert "Резюме RU." in report.content_md
        assert "Прогноз RU." in report.content_md
        assert "rule_based" not in (report.generated_by or "")

    def test_llm_failure_degrades_to_rule_based(self) -> None:
        from app.domains.news import reports as report_service  # noqa: PLC0415

        db = MagicMock()
        with (
            patch.object(report_service, "build_snapshot", return_value=_digest_snapshot()),
            patch.object(report_service, "_ai_digest", return_value=None),
        ):
            report = report_service.generate_report(db, use_llm=True)

        assert "i18n" not in report.data_snapshot
        assert report.generated_by == "rule_based"
        assert "🔮" not in report.content_md


class TestNewsApiI18n:
    def test_detail_includes_i18n_from_snapshot(self) -> None:
        from collections.abc import Generator  # noqa: PLC0415

        from fastapi.testclient import TestClient  # noqa: PLC0415

        from app.api.deps import get_current_client  # noqa: PLC0415
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415
        from app.models.enums import ReportStatus  # noqa: PLC0415

        report = MagicMock()
        report.id = 5
        report.title = "Обзор рынка — 2026-07-15"
        report.period_start = "2026-07-15"
        report.period_end = "2026-07-15"
        report.published_at = "2026-07-15T08:00:00+00:00"
        report.content_md = "тело"
        report.status = ReportStatus.published
        report.data_snapshot = {"i18n": {"summary": {"en": "Summary EN."}, "forecast": {}}}
        # The real Report ORM has no `i18n` attribute (schema default applies); a bare
        # MagicMock would auto-create one, so pin it to None like the ORM's absence.
        report.i18n = None

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = report

        app = create_app()

        def _db() -> Generator[Any, None, None]:
            yield db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_client] = lambda: MagicMock()
        client = TestClient(app)

        resp = client.get("/api/v1/webapp/news/5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["i18n"]["summary"]["en"] == "Summary EN."
