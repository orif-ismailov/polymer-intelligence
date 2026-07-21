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

    def test_setting_item_accepts_int_bool_str(self) -> None:
        """Regression: int settings (refresh interval) must serialize — value is bool|int|str."""
        from app.schemas.admin_settings import SettingItem  # noqa: PLC0415

        i = SettingItem.model_validate(
            {"key": "news_refresh_interval_minutes", "type": "int", "label": "x",
             "value": 60, "default": 60, "is_overridden": False}
        )
        assert i.value == 60 and isinstance(i.value, int)
        b = SettingItem.model_validate(
            {"key": "news_ai_enabled", "type": "bool", "label": "x",
             "value": True, "default": True, "is_overridden": False}
        )
        assert b.value is True  # bool stays bool, not coerced to 1


class TestNewsOpsApi:
    def test_stats(self) -> None:
        stats = {
            "total_sources": 5, "active_sources": 3, "failed_sources": 1,
            "last_scan": None, "last_published_report": None,
            "pending_ai_analysis": 2, "today_published_news": 4,
            "ai_enabled": True, "ai_status": "on",
            "ai_errors_recent": 0, "ai_last_error": None, "budget_used_pct": 12.5,
        }
        with patch("app.api.admin_settings.settings_service.get", return_value=True), \
             patch("app.api.admin_settings.report_service.news_admin_stats", return_value=stats):
            resp = _client().get("/api/v1/admin/news/stats")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_sources"] == 5 and body["ai_status"] == "on"
        assert body["budget_used_pct"] == 12.5

    def test_stats_surfaces_ai_error(self) -> None:
        """When the extractor is failing, ai_status='error' and the message is returned."""
        stats = {
            "total_sources": 3, "active_sources": 3, "failed_sources": 0,
            "last_scan": None, "last_published_report": None,
            "pending_ai_analysis": 0, "today_published_news": 0,
            "ai_enabled": True, "ai_status": "error", "ai_errors_recent": 4,
            "ai_last_error": "Error code: 400 - credit balance too low", "budget_used_pct": 100.0,
        }
        with patch("app.api.admin_settings.settings_service.get", return_value=True), \
             patch("app.api.admin_settings.report_service.news_admin_stats", return_value=stats):
            resp = _client().get("/api/v1/admin/news/stats")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ai_status"] == "error"
        assert body["ai_errors_recent"] == 4
        assert "credit balance" in body["ai_last_error"]
        assert body["budget_used_pct"] == 100.0

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

    def test_run_parser_enqueues_and_lists_sources(self) -> None:
        with patch("app.api.admin_settings.source_service.enabled_rss_source_names",
                   return_value=["World Petro", "Uzbek Petro"]), \
             patch("app.tasks.celery_app.celery_app.send_task") as mock_send:
            resp = _client().post("/api/v1/admin/news/run-parser")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["enqueued"] == ["rss_fetch"]
        assert body["sources"] == ["World Petro", "Uzbek Petro"]
        assert body["count"] == 2
        mock_send.assert_called_once()

    def test_activity(self) -> None:
        act = [{
            "id": 1, "name": "World Petro", "adapter": "rss", "group_name": "Global",
            "is_enabled": True, "last_fetch_at": None, "last_success_at": None,
            "consecutive_failures": 0, "raw_24h": 5, "news_24h": 3,
        }]
        with patch("app.api.admin_settings.source_service.news_source_activity", return_value=act):
            resp = _client().get("/api/v1/admin/news/activity")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body[0]["name"] == "World Petro"
        assert body[0]["raw_24h"] == 5 and body[0]["news_24h"] == 3


class TestSourceGroupsApi:
    def test_list_groups(self) -> None:
        groups = [{"group": "Uzbek news", "total": 3, "active": 2}, {"group": None, "total": 1, "active": 0}]
        with patch("app.api.admin_sources.source_service.list_source_groups", return_value=groups):
            resp = _client().get("/api/v1/admin/source-groups")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0] == {"group": "Uzbek news", "total": 3, "active": 2}

    def test_sources_brief(self) -> None:
        brief = [{"id": 5, "name": "UzPetro", "adapter": "rss", "country": "UZ",
                  "group_name": "Uzbek news", "is_enabled": True}]
        with patch("app.api.admin_sources.source_service.list_sources_brief", return_value=brief):
            resp = _client().get("/api/v1/admin/sources/brief")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["group_name"] == "Uzbek news"

    def test_set_group(self) -> None:
        updated = {"id": 5, "name": "UzPetro", "adapter": "rss", "country": "UZ",
                   "group_name": "Global news", "is_enabled": True}
        with patch("app.api.admin_sources.source_service.set_source_group", return_value=True), \
             patch("app.api.admin_sources.source_service.list_sources_brief", return_value=[updated]):
            resp = _client().put("/api/v1/admin/sources/5/group", json={"group": "Global news"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["group_name"] == "Global news"

    def test_set_group_404(self) -> None:
        with patch("app.api.admin_sources.source_service.set_source_group", return_value=False):
            resp = _client().put("/api/v1/admin/sources/999/group", json={"group": "X"})
        assert resp.status_code == 404
