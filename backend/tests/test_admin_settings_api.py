"""
Tests for the Phase 8d/8e admin settings + news-ops API (mocked db/auth).

- /admin/settings GET/PUT require admin; PUT maps KeyError/ValueError → 400.
- /admin/news/stats, /pending, /{id}/approve|reject are analyst-or-admin.
DB + services are mocked — no Postgres.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _app():  # noqa: ANN202
    from app.api.deps import require_admin, require_analyst_or_admin  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    def _db() -> Generator[Any, None, None]:
        yield MagicMock()

    application = create_app()
    application.dependency_overrides[get_db] = _db
    application.dependency_overrides[require_admin] = lambda: MagicMock(id=3)
    application.dependency_overrides[require_analyst_or_admin] = lambda: MagicMock(id=3)
    return application


def _client() -> TestClient:
    with patch("app.api.health._check_redis", return_value="ok"):
        return TestClient(_app())


_SETTING = {
    "key": "news_ai_enabled", "type": "bool", "label": "AI summaries in reports",
    "value": True, "default": True, "is_overridden": False,
}


class TestSettingsApi:
    def test_list_settings(self) -> None:
        with patch("app.api.admin_settings.settings_service.get_all", return_value=[_SETTING]):
            resp = _client().get("/api/v1/admin/settings")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["key"] == "news_ai_enabled"

    def test_list_settings_requires_admin(self) -> None:
        from app.core.db import get_db  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        def _db() -> Generator[Any, None, None]:
            yield MagicMock()

        app = create_app()
        app.dependency_overrides[get_db] = _db  # no auth override → must be rejected
        with patch("app.api.health._check_redis", return_value="ok"), TestClient(
            app, raise_server_exceptions=False
        ) as tc:
            resp = tc.get("/api/v1/admin/settings")
        assert resp.status_code == 401, resp.text

    def test_update_settings(self) -> None:
        updated = [{**_SETTING, "value": False, "is_overridden": True}]
        with patch("app.api.admin_settings.settings_service.set_many", return_value=updated) as mock_set:
            resp = _client().put("/api/v1/admin/settings", json={"news_ai_enabled": False})
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["value"] is False
        assert mock_set.call_args.args[1] == {"news_ai_enabled": False}

    def test_update_empty_is_400(self) -> None:
        resp = _client().put("/api/v1/admin/settings", json={})
        assert resp.status_code == 400

    def test_update_unknown_key_is_400(self) -> None:
        with patch("app.api.admin_settings.settings_service.set_many", side_effect=KeyError("nope")):
            resp = _client().put("/api/v1/admin/settings", json={"nope": 1})
        assert resp.status_code == 400
        assert "Unknown setting" in resp.json()["detail"]


class TestNewsOpsApi:
    def test_stats(self) -> None:
        stats = {
            "total_sources": 5, "active_sources": 3, "failed_sources": 1,
            "last_scan": None, "last_published_report": None,
            "pending_ai_analysis": 2, "today_published_news": 4,
            "ai_enabled": True, "ai_status": "on",
        }
        with patch("app.api.admin_settings.settings_service.get", return_value=True), \
             patch("app.api.admin_settings.report_service.news_admin_stats", return_value=stats):
            resp = _client().get("/api/v1/admin/news/stats")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_sources"] == 5 and body["ai_status"] == "on"

    def test_pending_list(self) -> None:
        item = {"id": 7, "headline": "Pending story", "importance": "high",
                "summary": "s", "source_name": "TG", "published_at": "2026-07-21T00:00:00+00:00"}
        with patch("app.api.admin_settings.news_service.list_pending_news", return_value=[item]):
            resp = _client().get("/api/v1/admin/news/pending")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["id"] == 7

    def test_approve_ok(self) -> None:
        with patch("app.api.admin_settings.news_service.set_news_approval", return_value=True):
            resp = _client().post("/api/v1/admin/news/7/approve")
        assert resp.status_code == 200
        assert resp.json() == {"id": 7, "approval": "approved"}

    def test_approve_404_when_missing(self) -> None:
        with patch("app.api.admin_settings.news_service.set_news_approval", return_value=False):
            resp = _client().post("/api/v1/admin/news/999/approve")
        assert resp.status_code == 404

    def test_reject_ok(self) -> None:
        with patch("app.api.admin_settings.news_service.set_news_approval", return_value=True):
            resp = _client().post("/api/v1/admin/news/7/reject")
        assert resp.status_code == 200
        assert resp.json()["approval"] == "rejected"

    def test_run_parser_enqueues(self) -> None:
        with patch("app.tasks.celery_app.celery_app.send_task") as mock_send:
            resp = _client().post("/api/v1/admin/news/run-parser")
        assert resp.status_code == 200, resp.text
        assert resp.json()["enqueued"] == ["rss_fetch"]
        mock_send.assert_called_once()
