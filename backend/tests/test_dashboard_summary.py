"""
Tests for GET /dashboard/summary (dashboard home overview).

Auth + mounting are covered here; the data-shape correctness is exercised
end-to-end by the dashboard Playwright e2e against a live seeded DB (the service
runs raw aggregate SQL that a mocked session can't meaningfully stand in for).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_summary_requires_staff_auth(client: TestClient) -> None:
    """Unauthenticated request is rejected (staff-only)."""
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


def test_summary_route_mounted() -> None:
    """The /api/v1/dashboard/summary route is registered on the app."""
    from app.main import create_app  # noqa: PLC0415

    app = create_app()
    assert app.url_path_for("dashboard_summary") == "/api/v1/dashboard/summary"
