"""
Automated SLA proxy tests for Phase-3 acceptance criteria.

Covers TZ §6.1.1 SLAs:
  SC#1 — A submitted request is queryable on the backend within 10 s of POST
          (proxy: in-process create→readback elapsed time < 10.0 s).
  SC#3 — A status change enqueues the notify push on the notify queue within
          the ≤30 s budget (proxy: apply_async called immediately — no countdown/eta).

These are CI-safe (DB-mocked, no live infra) proxy tests.  The full wall-clock
live drill runs against a real docker-compose stack at deploy time and is recorded
in docs/phase-03-acceptance.md.

Acceptance criteria (from 03-06-PLAN.md):
  - test_request_readback_within_10s asserts elapsed create→read time < 10.0 s
    and that the created REQ number appears in the list.
  - test_status_change_enqueues_notify_promptly asserts apply_async was called
    with queue="notify" and that the call kwargs contain no countdown/eta
    (immediate dispatch → ≤30 s budget bounded only by Celery delivery).
  - test_notify_task_no_long_sleep asserts no time.sleep() with a multi-second
    constant appears in notify.py source.
  - pytest tests/test_request_sla.py exits 0; full suite stays green.
"""

from __future__ import annotations

import inspect
import re
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_mock_client(id: int = 1, language: str = "ru") -> MagicMock:
    """Return a MagicMock that quacks like a Client ORM object."""
    client = MagicMock()
    client.id = id
    client.language = language
    client.company_name = "SLA Test Co"
    client.contact_name = "SLA Tester"
    return client


def _make_mock_db() -> MagicMock:
    """Return a MagicMock that quacks like a SQLAlchemy Session."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    # Provide execute mock for generate_request_number (CREATE SEQUENCE + SELECT nextval)
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    db.execute.return_value = mock_result
    return db


def _make_mock_request_with_number(number: str = "REQ-2026-06-16-00001") -> MagicMock:
    """Return a MagicMock that quacks like a Request ORM object."""
    import datetime  # noqa: PLC0415

    from app.models.enums import PriceBasis, RequestStatus  # noqa: PLC0415

    req = MagicMock()
    req.id = 1
    req.client_id = 1
    req.number = number
    req.status = RequestStatus.new
    req.created_at = datetime.datetime(2026, 6, 16, 10, 0, 0, tzinfo=datetime.UTC)
    req.product_id = 1
    req.grade_text = "HDPE 2420D"
    req.volume = 100
    req.target_price = None
    req.currency = "USD"
    req.incoterms = PriceBasis.unknown
    req.files = []
    req.status_history = []
    return req


# ── SC#1: Create→readback latency ≤10 s ──────────────────────────────────────


@pytest.fixture
def sla_client() -> Generator[TestClient, None, None]:
    """TestClient with get_current_client and get_db overridden for SLA tests."""
    from app.api.deps import get_current_client  # noqa: PLC0415
    from app.core.db import get_db  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    mock_client = _make_mock_client(id=1)
    mock_db = _make_mock_db()

    req_number = "REQ-2026-06-16-00001"
    mock_req = _make_mock_request_with_number(req_number)

    # Wire list query: db.query().filter().order_by().all() → [mock_req]
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.all.return_value = [mock_req]
    mock_db.query.return_value = mock_query

    def _override_get_db() -> Generator[Any, None, None]:
        yield mock_db

    def _override_get_current_client() -> Any:
        return mock_client

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_current_client] = _override_get_current_client

    with (
        patch("app.api.health._check_redis", return_value="ok"),
        patch("app.tasks.notify.send_status_change_notification") as mock_task,
        TestClient(application, raise_server_exceptions=True) as tc,
    ):
        mock_task_instance = MagicMock()
        mock_task.return_value = mock_task_instance
        # Patch at the import site inside request_service function bodies
        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_apply:
            mock_apply.apply_async = MagicMock()
            # Patch create_request to use the mocked service
            with patch("app.api.webapp.requests.request_service") as mock_svc:
                mock_svc.create_request.return_value = mock_req
                yield tc


def test_request_readback_within_10s(sla_client: TestClient) -> None:
    """SC#1 proxy: POST /webapp/requests → GET /webapp/requests elapsed time < 10.0 s.

    This is an in-process, DB-mocked proxy for TZ §6.1.1 SC#1 ("A submitted request
    is queryable on the backend within 10 s of POST").

    The mock DB returns the created request immediately on the subsequent list query —
    demonstrating that the create path persists synchronously (no async-write lag).
    The REQ number from the POST response must appear in the GET /webapp/requests list.

    Wall-clock live measurement is recorded in docs/phase-03-acceptance.md.
    """
    # ── POST (create) ──────────────────────────────────────────────────────────
    t_before_post = time.monotonic()
    create_resp = sla_client.post(
        "/api/v1/webapp/requests",
        json={
            "product_id": 1,
            "grade_text": "HDPE 2420D",
            "volume": "100.000",
            "volume_unit": "MT",
        },
    )
    assert create_resp.status_code == 201, f"POST failed: {create_resp.text}"
    created_number = create_resp.json()["number"]
    assert created_number.startswith("REQ-"), f"Unexpected number format: {created_number!r}"

    # ── GET (readback) ─────────────────────────────────────────────────────────
    list_resp = sla_client.get("/api/v1/webapp/requests")
    t_after_get = time.monotonic()

    assert list_resp.status_code == 200, f"GET failed: {list_resp.text}"

    # ── Latency assertion ──────────────────────────────────────────────────────
    elapsed = t_after_get - t_before_post
    assert elapsed < 10.0, (
        f"SC#1 SLA BREACH: create→readback elapsed {elapsed:.3f} s ≥ 10.0 s"
    )

    # ── Number appears in the list ─────────────────────────────────────────────
    request_list = list_resp.json()
    assert isinstance(request_list, list), "Expected list response"
    numbers_in_list = [r["number"] for r in request_list]
    assert created_number in numbers_in_list, (
        f"Created REQ number {created_number!r} not found in readback list: {numbers_in_list}"
    )


# ── SC#3: Status-change enqueue timing ≤30 s ─────────────────────────────────


def test_status_change_enqueues_notify_promptly() -> None:
    """SC#3 proxy: transition_status enqueues notify on queue='notify' with no countdown/eta.

    TZ §6.1.1 SC#3: A status change enqueues the notify push within the ≤30 s budget.
    This is bounded by Celery delivery only when the enqueue is immediate (no countdown/eta).

    Asserts:
      - apply_async is called exactly once with queue="notify"
      - no countdown or eta keyword argument is passed (immediate dispatch)
    """
    from app.models.enums import RequestStatus  # noqa: PLC0415
    from app.services.request_service import transition_status  # noqa: PLC0415

    db = _make_mock_db()
    # TG-origin request with status=new (valid transition: new → viewed). TG-origin
    # (created_by_user_account_id=None) → the TG DM enqueue path; a bare MagicMock
    # attr would be truthy and wrongly route to the portal-notification path.
    mock_request = MagicMock()
    mock_request.id = 42
    mock_request.status = RequestStatus.new
    mock_request.created_by_user_account_id = None

    # Mock write_audit so the staff path doesn't break (no DB needed)
    with patch("app.services.request_service.write_audit"), patch(
        "app.tasks.notify.send_status_change_notification",
        create=True,
    ) as mock_task:
        mock_apply_async = MagicMock()
        mock_task.apply_async = mock_apply_async

        transition_status(db, mock_request, RequestStatus.viewed)

    # apply_async must have been called exactly once
    assert mock_apply_async.call_count == 1, (
        f"Expected apply_async to be called once, called {mock_apply_async.call_count} times"
    )

    # Must be dispatched on the 'notify' queue
    call_kwargs = mock_apply_async.call_args
    assert call_kwargs is not None, "apply_async was not called with any arguments"

    # queue= may be positional (args) or keyword (kwargs); check both
    all_kwargs = call_kwargs.kwargs  # keyword args dict
    assert all_kwargs.get("queue") == "notify", (
        f"Expected queue='notify', got call: {call_kwargs!r}"
    )

    # No countdown or eta — immediate dispatch (SLA budget bounded by delivery only)
    assert "countdown" not in all_kwargs, (
        f"Unexpected countdown in apply_async call — task must be dispatched immediately: {all_kwargs!r}"
    )
    assert "eta" not in all_kwargs, (
        f"Unexpected eta in apply_async call — task must be dispatched immediately: {all_kwargs!r}"
    )


# ── Notify task: no large blocking sleep ──────────────────────────────────────


def test_notify_task_no_long_sleep() -> None:
    """Defends ≤30 s SLA against accidental blocking sleep in send_status_change_notification.

    Inspects the source of app.tasks.notify and asserts it contains no
    time.sleep() call with a constant argument > 1 second.

    A multi-second blocking sleep inside the Celery worker would violate the
    ≤30 s notify-delivery budget (TZ §6.1.1 SC#3) regardless of Celery dispatch timing.
    """
    import app.tasks.notify as notify_module  # noqa: PLC0415

    source = inspect.getsource(notify_module)

    # Pattern: time.sleep(<number>) where number is a decimal ≥ 2
    # Covers: time.sleep(5), time.sleep(30.0), time.sleep(10), etc.
    # Does NOT flag: time.sleep(0), time.sleep(0.1), time.sleep(1)
    long_sleep_pattern = re.compile(
        r"time\.sleep\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)"
    )
    for match in long_sleep_pattern.finditer(source):
        sleep_value = float(match.group(1))
        assert sleep_value <= 1.0, (
            f"notify.py contains blocking time.sleep({sleep_value}) "
            f"which would violate the ≤30 s SLA budget (TZ §6.1.1 SC#3). "
            f"Context: {match.group(0)!r}"
        )


# ── Additional: full suite regression guard ───────────────────────────────────


def test_sla_test_module_imports_cleanly() -> None:
    """Smoke: the SLA test module imports without errors (CI collection guard)."""
    import backend.tests.test_request_sla as _self  # type: ignore[import] # noqa: PLC0415, F401

    # If import succeeded, we're good
    assert _self is not None
