"""
Tests for POST /admin/sources/{id}/reprocess.

Resets a source's previously-dropped raw_items (irrelevant/failed/budget_deferred)
back to 'pending' and re-enqueues the adapter's parse task. DB + Celery are mocked —
no Postgres, no broker.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client(source_row: Any, updated_ids: list[int] | None = None) -> tuple[TestClient, MagicMock]:
    """Build a TestClient with get_db + the staff identity overridden.

    db.execute is called at most twice: the SELECT (→ .first()) and, when the source
    is supported, the UPDATE ... RETURNING id (→ .scalars()).
    """
    from app.api.deps import get_current_staff_user  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    select_result = MagicMock()
    select_result.first.return_value = source_row
    update_result = MagicMock()
    update_result.scalars.return_value = list(updated_ids or [])

    mock_db = MagicMock()
    mock_db.execute.side_effect = [select_result, update_result]

    def _override_db() -> Generator[Any, None, None]:
        yield mock_db

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_staff_user] = lambda: MagicMock(
        id=1, is_admin=True, is_active=True
    )
    return TestClient(app, raise_server_exceptions=True), mock_db


class TestReprocessSource:
    def test_requeues_dropped_rows_and_dispatches_correct_task(self) -> None:
        """xarid source → resets 3 rows and enqueues parse_xarid_item for each."""
        with patch("app.tasks.celery_app.celery_app.send_task") as mock_send:
            client, _ = _client((5, "xarid_tenders", {}), updated_ids=[10, 11, 12])
            resp = client.post("/api/v1/admin/sources/5/reprocess")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {
            "source_id": 5,
            "adapter": "xarid_tenders",
            "parse_task": "parse_xarid_item",
            "requeued": 3,
        }
        assert mock_send.call_count == 3
        # every dispatch targets the xarid parser on the parse queue
        for call in mock_send.call_args_list:
            assert call.args[0] == "parse_xarid_item"
            assert call.kwargs.get("queue") == "parse"

    def test_uzex_source_routes_to_rule_parser(self) -> None:
        with patch("app.tasks.celery_app.celery_app.send_task") as mock_send:
            client, _ = _client((1, "uzex_deals", {}), updated_ids=[7])
            resp = client.post("/api/v1/admin/sources/1/reprocess")

        assert resp.status_code == 200, resp.text
        assert resp.json()["parse_task"] == "parse_raw_item"
        assert mock_send.call_args.args[0] == "parse_raw_item"

    def test_news_source_routes_to_news_parser(self) -> None:
        """A content_kind='news' source re-parses via parse_news_item regardless of adapter."""
        with patch("app.tasks.celery_app.celery_app.send_task") as mock_send:
            client, _ = _client((9, "rss", {"content_kind": "news"}), updated_ids=[88])
            resp = client.post("/api/v1/admin/sources/9/reprocess")

        assert resp.status_code == 200, resp.text
        assert resp.json()["parse_task"] == "parse_news_item"
        assert mock_send.call_args.args[0] == "parse_news_item"

    def test_no_dropped_rows_requeues_zero(self) -> None:
        with patch("app.tasks.celery_app.celery_app.send_task") as mock_send:
            client, _ = _client((5, "xarid_tenders", {}), updated_ids=[])
            resp = client.post("/api/v1/admin/sources/5/reprocess")

        assert resp.status_code == 200, resp.text
        assert resp.json()["requeued"] == 0
        mock_send.assert_not_called()

    def test_unknown_source_returns_404(self) -> None:
        with patch("app.tasks.celery_app.celery_app.send_task") as mock_send:
            client, _ = _client(None)
            resp = client.post("/api/v1/admin/sources/999/reprocess")

        assert resp.status_code == 404
        mock_send.assert_not_called()

    def test_unsupported_adapter_returns_400(self) -> None:
        """cbu_rates writes fx_rates directly (no raw_items→signals) → 400, no dispatch."""
        with patch("app.tasks.celery_app.celery_app.send_task") as mock_send:
            client, _ = _client((4, "cbu_rates", {}))
            resp = client.post("/api/v1/admin/sources/4/reprocess")

        assert resp.status_code == 400
        mock_send.assert_not_called()
