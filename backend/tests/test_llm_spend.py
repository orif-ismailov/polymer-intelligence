"""
Tests for GET /admin/llm-spend — today's budget + per-model spend breakdown.

daily_spend (Redis) and db.execute (parse_runs aggregate) are mocked.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client(model_rows: list[tuple[str, int, int, int]]) -> TestClient:
    """TestClient with get_db + require_admin overridden; db.execute→fetchall returns rows."""
    from app.api.deps import require_admin  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    result = MagicMock()
    result.fetchall.return_value = model_rows
    mock_db = MagicMock()
    mock_db.execute.return_value = result

    def _override_db() -> Generator[Any, None, None]:
        yield mock_db

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=True)


def test_llm_spend_budget_and_breakdown() -> None:
    rows = [
        ("claude-haiku-4-5", 200, 300_000, 60_000),   # 0.3 in + 0.3 out = $0.60
        ("claude-sonnet-4-5", 3, 5_000, 6_000),       # 0.015 in + 0.09 out = $0.105
    ]
    with patch("parsing.budget.daily_spend", return_value=120_000):
        resp = _client(rows).get("/api/v1/admin/llm-spend?days=7")

    assert resp.status_code == 200, resp.text
    b = resp.json()
    assert b["today_tokens"] == 120_000
    assert b["daily_limit_tokens"] == 500_000       # test env default
    assert b["remaining_tokens"] == 380_000
    assert b["window_days"] == 7
    assert b["total_calls"] == 203
    assert b["total_tokens_in"] == 305_000
    assert len(b["by_model"]) == 2

    haiku = next(m for m in b["by_model"] if m["model"] == "claude-haiku-4-5")
    assert abs(haiku["est_cost_usd"] - 0.60) < 1e-6   # exact-count × assumed rate
    assert abs(b["est_cost_usd"] - 0.705) < 1e-6
    # rates are echoed so the estimate is transparent/correctable
    assert "claude-haiku-4-5" in b["assumed_rates_usd_per_mtok"]


def test_llm_spend_empty_window() -> None:
    with patch("parsing.budget.daily_spend", return_value=0):
        resp = _client([]).get("/api/v1/admin/llm-spend")

    assert resp.status_code == 200, resp.text
    b = resp.json()
    assert b["total_calls"] == 0
    assert b["by_model"] == []
    assert b["est_cost_usd"] == 0.0
    assert b["pct_used"] == 0.0
