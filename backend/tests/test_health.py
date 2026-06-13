"""
Unit tests for GET /api/v1/health.

Tests run with mocked db and redis so no live infrastructure is needed.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient) -> None:
        """GET /api/v1/health must return HTTP 200."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_response_has_db_key(self, client: TestClient) -> None:
        """Response JSON must contain a 'db' key."""
        response = client.get("/api/v1/health")
        body = response.json()
        assert "db" in body

    def test_health_response_has_redis_key(self, client: TestClient) -> None:
        """Response JSON must contain a 'redis' key."""
        response = client.get("/api/v1/health")
        body = response.json()
        assert "redis" in body

    def test_health_response_has_status_key(self, client: TestClient) -> None:
        """Response JSON must contain an overall 'status' key."""
        response = client.get("/api/v1/health")
        body = response.json()
        assert "status" in body

    def test_health_all_ok_when_deps_healthy(self, client: TestClient) -> None:
        """When both db and redis are ok, status should be 'ok'."""
        response = client.get("/api/v1/health")
        body = response.json()
        assert body["db"] == "ok"
        assert body["redis"] == "ok"
        assert body["status"] == "ok"

    def test_health_degraded_when_db_error(self, client_db_error: TestClient) -> None:
        """When db check fails, status must be 'degraded' and db must be 'error'."""
        response = client_db_error.get("/api/v1/health")
        assert response.status_code == 200  # always 200
        body = response.json()
        assert body["db"] == "error"
        assert body["status"] == "degraded"

    def test_health_degraded_when_redis_error(self, client_redis_error: TestClient) -> None:
        """When redis check fails, status must be 'degraded' and redis must be 'error'."""
        response = client_redis_error.get("/api/v1/health")
        assert response.status_code == 200  # always 200
        body = response.json()
        assert body["redis"] == "error"
        assert body["status"] == "degraded"

    def test_health_response_no_sensitive_data(self, client: TestClient) -> None:
        """Health response must not leak connection strings or internal details.

        Security: T-01-02 — /health returns only status enums.
        """
        response = client.get("/api/v1/health")
        body_text = response.text
        # Verify no URL patterns or stack traces leaked
        assert "postgresql" not in body_text
        assert "redis://" not in body_text
        assert "Traceback" not in body_text
        assert "Exception" not in body_text

    def test_health_content_type_json(self, client: TestClient) -> None:
        """Response Content-Type must be application/json."""
        response = client.get("/api/v1/health")
        assert "application/json" in response.headers.get("content-type", "")

    def test_health_response_has_schema_version_key(self, client: TestClient) -> None:
        """Response JSON must contain a 'schema_version' key (may be null).

        REQ-nfr-observability: /health reports schema migration status.
        plan 01-02 requirement: schema_version field proves migrations applied.
        """
        response = client.get("/api/v1/health")
        body = response.json()
        assert "schema_version" in body
