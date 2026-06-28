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
        from app.services.report_service import _rule_based_summary

        up = {"products": [{"delta": 5.0}, {"delta": 2.0}, {"delta": -1.0}]}
        down = {"products": [{"delta": -5.0}, {"delta": -2.0}, {"delta": 1.0}]}
        assert "выросли" in _rule_based_summary(up)
        assert "снизились" in _rule_based_summary(down)
        assert "Недостаточно" in _rule_based_summary({"products": []})

    def test_render_markdown_contains_products_and_summary(self):
        from app.services.report_service import render_markdown

        md = render_markdown(self._snapshot(), "Тестовое резюме.")
        assert "Ежедневный обзор рынка" in md
        assert "HDPE" in md and "PP" in md
        assert "(+15)" in md  # positive delta sign
        assert "(-10)" in md
        assert "Тестовое резюме." in md
        assert "запросы — 14" in md


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
        with patch("app.api.webapp.news.report_service") as svc:
            svc.list_published.return_value = [_mock_report()]
            resp = news_client.get("/api/v1/webapp/news")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["title"].startswith("Обзор")

    def test_detail_404_when_not_published(self, news_client: TestClient):
        with patch("app.api.webapp.news.report_service") as svc:
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
            "app.api.reports.report_service"
        ) as svc, TestClient(application) as tc:
            svc.get_report.return_value = _mock_report(status="approved")
            svc.publish_report.return_value = _mock_report(status="published")
            resp = tc.post("/api/v1/admin/reports/5/publish")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "published"
