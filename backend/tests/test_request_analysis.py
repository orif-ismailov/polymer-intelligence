"""
Tests for the Phase-5 request AI analysis feature:

- request_analysis_service.analyze_request: LLM result → requests.ai, budget/flag/error paths.
- POST /requests/{id}/analyze endpoint: 200 / 403 (viewer) / 404 / 503 (disabled-or-budget).
- create_request enqueues the analysis task (fail-soft, flag-gated).

The LLM client and budget guard are mocked — no network, no Redis.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.test_dashboard_requests import (  # reuse the dashboard-requests harness
    _auth_headers,
    _make_mock_request,
    _make_staff_user,
)


def _fake_completion(tokens_in: int = 120, tokens_out: int = 40) -> MagicMock:
    completion = MagicMock()
    completion.usage = SimpleNamespace(
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    return completion


def _patch_service_internals(svc, result, completion=None):
    """Patch the LLM client + budget + context builder on the service module."""
    completion = completion or _fake_completion()
    svc._build_market_context = MagicMock(  # type: ignore[attr-defined]
        return_value={"request": {}, "market": {}, "price_analysis": None}
    )
    svc.check_and_reserve_tokens = MagicMock(return_value=None)  # type: ignore[attr-defined]
    svc.record_actual_tokens = MagicMock(return_value=None)  # type: ignore[attr-defined]
    svc._client.messages.create_with_completion = MagicMock(  # type: ignore[attr-defined]
        return_value=(result, completion)
    )


# ── Service ───────────────────────────────────────────────────────────────────


class TestAnalyzeRequestService:
    def test_populates_request_ai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.domains.requests import analysis as svc  # noqa: PLC0415
        from app.domains.requests.analysis_schemas import RequestAnalysisResult  # noqa: PLC0415

        monkeypatch.setattr(svc.settings, "REQUEST_AI_ANALYSIS_ENABLED", True)
        result = RequestAnalysisResult(
            match_score=0.82, demand_level="high", recommendation="Передать 2 продавцам."
        )
        with patch.object(svc, "_build_market_context", return_value={"a": 1}), \
             patch.object(svc, "check_and_reserve_tokens"), \
             patch.object(svc, "record_actual_tokens") as rec, \
             patch.object(
                 svc._client.messages,
                 "create_with_completion",
                 return_value=(result, _fake_completion(120, 40)),
             ):
            db = MagicMock()
            req = MagicMock(id=14)
            ai = svc.analyze_request(db, req)

        assert ai is not None
        assert ai["match_score"] == 0.82
        assert ai["demand_level"] == "high"
        assert ai["recommendation"] == "Передать 2 продавцам."
        assert ai["model"] == svc.settings.REQUEST_AI_ANALYSIS_MODEL
        assert "analyzed_at" in ai
        # Stamped onto the request + flushed, never committed (service axiom).
        assert req.ai == ai
        db.flush.assert_called_once()
        db.commit.assert_not_called()
        # Actual token usage reconciled against the reservation.
        rec.assert_called_once()
        assert rec.call_args.args[1] == 160  # tokens_in + tokens_out

    def test_disabled_flag_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.domains.requests import analysis as svc  # noqa: PLC0415

        monkeypatch.setattr(svc.settings, "REQUEST_AI_ANALYSIS_ENABLED", False)
        db, req = MagicMock(), MagicMock(id=1)
        with patch.object(svc._client.messages, "create_with_completion") as llm:
            assert svc.analyze_request(db, req) is None
        llm.assert_not_called()  # no LLM spend when disabled

    def test_budget_exceeded_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.domains.requests import analysis as svc  # noqa: PLC0415
        from parsing.schemas import BudgetExceeded  # noqa: PLC0415

        monkeypatch.setattr(svc.settings, "REQUEST_AI_ANALYSIS_ENABLED", True)
        with patch.object(svc, "_build_market_context", return_value={}), \
             patch.object(svc, "check_and_reserve_tokens", side_effect=BudgetExceeded("nope")), \
             patch.object(svc._client.messages, "create_with_completion") as llm:
            db, req = MagicMock(), MagicMock(id=2)
            assert svc.analyze_request(db, req) is None
            llm.assert_not_called()  # budget guard blocks the call

    def test_llm_error_releases_reservation_and_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.domains.requests import analysis as svc  # noqa: PLC0415

        monkeypatch.setattr(svc.settings, "REQUEST_AI_ANALYSIS_ENABLED", True)
        with patch.object(svc, "_build_market_context", return_value={}), \
             patch.object(svc, "check_and_reserve_tokens"), \
             patch.object(svc, "record_actual_tokens") as rec, \
             patch.object(
                 svc._client.messages, "create_with_completion", side_effect=RuntimeError("boom")
             ):
            db, req = MagicMock(), MagicMock(id=3)
            assert svc.analyze_request(db, req) is None
            rec.assert_called_once_with(svc.settings.REQUEST_AI_TOKEN_ESTIMATE, 0)


# ── Endpoint: POST /requests/{id}/analyze ───────────────────────────────────────


def _client_with_lookup(auth_user: MagicMock, entity: MagicMock | None):
    """TestClient whose db returns auth_user for the first query and `entity` after."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    mock_db = MagicMock()
    call_count = [0]

    def query_side_effect(_model):
        call_count[0] += 1
        q = MagicMock()
        q.filter.return_value.first.return_value = auth_user if call_count[0] == 1 else entity
        return q

    mock_db.query.side_effect = query_side_effect

    def _override_db():
        yield mock_db

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    return TestClient(app, raise_server_exceptions=False)


class TestAnalyzeEndpoint:
    def test_admin_triggers_analysis_returns_detail(self) -> None:
        admin = _make_staff_user("admin", user_id=1)
        req = _make_mock_request(id=42)

        def fake_analyze(_db, request):
            request.ai = {
                "match_score": 0.7,
                "demand_level": "medium",
                "recommendation": "Контроффер +8%.",
            }
            return request.ai

        client = _client_with_lookup(admin, req)
        with patch(
            "app.domains.requests.analysis.analyze_request", side_effect=fake_analyze
        ), patch(
            "app.domains.pricing.analysis.compute_price_analysis", return_value=None
        ):
            resp = client.post("/api/v1/requests/42/analyze", headers=_auth_headers(1, "admin"))

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ai"]["demand_level"] == "medium"
        assert body["ai"]["match_score"] == 0.7

    def test_viewer_forbidden(self) -> None:
        viewer = _make_staff_user("viewer", user_id=2)
        client = _client_with_lookup(viewer, _make_mock_request(id=42))
        resp = client.post("/api/v1/requests/42/analyze", headers=_auth_headers(2, "viewer"))
        assert resp.status_code == 403

    def test_missing_request_404(self) -> None:
        admin = _make_staff_user("admin", user_id=1)
        client = _client_with_lookup(admin, None)
        resp = client.post("/api/v1/requests/99999/analyze", headers=_auth_headers(1, "admin"))
        assert resp.status_code == 404

    def test_disabled_or_budget_returns_503(self) -> None:
        admin = _make_staff_user("admin", user_id=1)
        req = _make_mock_request(id=42)
        client = _client_with_lookup(admin, req)
        with patch(
            "app.domains.requests.analysis.analyze_request", return_value=None
        ):
            resp = client.post("/api/v1/requests/42/analyze", headers=_auth_headers(1, "admin"))
        assert resp.status_code == 503


# ── Trigger: create_request enqueues analysis ───────────────────────────────────


class TestAnalysisTrigger:
    def test_enqueue_soft_dispatches_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.domains.requests import service as request_service  # noqa: PLC0415

        monkeypatch.setattr(request_service.settings, "REQUEST_AI_ANALYSIS_ENABLED", True)
        with patch("app.tasks.request_analysis.analyze_request_ai") as task:
            request_service._enqueue_analysis_soft(14)
        task.apply_async.assert_called_once()
        assert task.apply_async.call_args.kwargs["queue"] == "parse"

    def test_enqueue_soft_noop_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.domains.requests import service as request_service  # noqa: PLC0415

        monkeypatch.setattr(request_service.settings, "REQUEST_AI_ANALYSIS_ENABLED", False)
        with patch("app.tasks.request_analysis.analyze_request_ai") as task:
            request_service._enqueue_analysis_soft(14)
        task.apply_async.assert_not_called()

    def test_enqueue_soft_swallows_broker_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.domains.requests import service as request_service  # noqa: PLC0415

        monkeypatch.setattr(request_service.settings, "REQUEST_AI_ANALYSIS_ENABLED", True)
        with patch("app.tasks.request_analysis.analyze_request_ai") as task:
            task.apply_async.side_effect = RuntimeError("broker down")
            # Must not raise — analysis enqueue is best-effort.
            request_service._enqueue_analysis_soft(14)
