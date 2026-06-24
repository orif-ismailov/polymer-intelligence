"""
Tests for backend/app/services/request_service.py.

TDD RED phase: these tests are written BEFORE the implementation.
They will all fail until request_service.py is created.

Covers:
- generate_request_number: format regex + monotonic counter
- VALID_TRANSITIONS: rejects new→closed, accepts in_progress→{offer_sent,matched,closed,cancelled}
- create_request: inserts Request + history row, enqueues notify (apply_async), never commits
- transition_status: enforces machine, writes history, raises ValueError on invalid transition
- client_facing_status: all 7 RequestStatus values
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mock_db() -> MagicMock:
    """Return a MagicMock that quacks like a SQLAlchemy Session."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    return db


def _make_mock_client(id: int = 1) -> MagicMock:
    """Return a MagicMock that quacks like a Client ORM object."""
    client = MagicMock()
    client.id = id
    return client


def _make_mock_request(status_val: str = "in_progress", id: int = 42) -> MagicMock:
    """Return a MagicMock that quacks like a Request ORM object."""
    from app.models.enums import RequestStatus  # noqa: PLC0415
    req = MagicMock()
    req.id = id
    req.status = RequestStatus(status_val)
    return req


def _make_request_create(**kwargs) -> MagicMock:
    """Return a RequestCreate schema instance with sane defaults."""
    import decimal

    from app.schemas.webapp import RequestCreate  # noqa: PLC0415
    data = {
        "product_id": 1,
        "grade_text": "HDPE 2420D",
        "volume": decimal.Decimal("100"),
        **kwargs,
    }
    return RequestCreate(**data)


# ── Number generation ──────────────────────────────────────────────────────────

class TestGenerateRequestNumber:
    """generate_request_number(db) produces REQ-YYYY-MM-DD-NNNNN format."""

    def test_number_format_matches_regex(self):
        """Number matches REQ-YYYY-MM-DD-NNNNN pattern exactly."""
        from app.services.request_service import generate_request_number  # noqa: PLC0415

        db = _make_mock_db()
        # Mock the execute result for CREATE SEQUENCE IF NOT EXISTS and SELECT nextval
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        db.execute.return_value = mock_result

        number = generate_request_number(db)

        pattern = r"^REQ-\d{4}-\d{2}-\d{2}-\d{5}$"
        assert re.match(pattern, number), f"Number '{number}' does not match REQ-YYYY-MM-DD-NNNNN"

    def test_number_counter_increments(self):
        """Consecutive calls with mock nextval 1 then 2 yield NNNNN and NNNNN+1."""
        from app.services.request_service import generate_request_number  # noqa: PLC0415

        db = _make_mock_db()
        # Return 1 then 2 for nextval; CREATE SEQUENCE IF NOT EXISTS is a side-effect call
        mock_result_1 = MagicMock()
        mock_result_1.scalar.return_value = 1
        mock_result_2 = MagicMock()
        mock_result_2.scalar.return_value = 2
        # Three execute calls per generate_request_number:
        # pg_advisory_xact_lock + CREATE SEQUENCE + SELECT nextval
        db.execute.side_effect = [
            MagicMock(),          # pg_advisory_xact_lock call 1
            MagicMock(),          # CREATE SEQUENCE IF NOT EXISTS call 1
            mock_result_1,        # SELECT nextval call 1
            MagicMock(),          # pg_advisory_xact_lock call 2
            MagicMock(),          # CREATE SEQUENCE IF NOT EXISTS call 2
            mock_result_2,        # SELECT nextval call 2
        ]

        n1 = generate_request_number(db)
        n2 = generate_request_number(db)

        suffix1 = int(n1.split("-")[-1])
        suffix2 = int(n2.split("-")[-1])
        assert suffix2 == suffix1 + 1, f"Expected {suffix1 + 1} but got {suffix2}"

    def test_number_five_digit_zero_padded(self):
        """Counter is zero-padded to 5 digits (e.g. 00007 not 7)."""
        from app.services.request_service import generate_request_number  # noqa: PLC0415

        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 7
        db.execute.return_value = mock_result

        number = generate_request_number(db)

        suffix = number.split("-")[-1]
        assert len(suffix) == 5, f"Suffix '{suffix}' is not 5 chars"
        assert suffix == "00007", f"Expected '00007' but got '{suffix}'"


# ── VALID_TRANSITIONS ─────────────────────────────────────────────────────────

class TestValidTransitions:
    """VALID_TRANSITIONS dict encodes the dev-spec §3 status machine exactly."""

    def test_new_can_only_go_to_viewed(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert VALID_TRANSITIONS[RequestStatus.new] == {RequestStatus.viewed}

    def test_viewed_can_only_go_to_in_progress(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert VALID_TRANSITIONS[RequestStatus.viewed] == {RequestStatus.in_progress}

    def test_in_progress_allowed_targets(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        expected = {
            RequestStatus.offer_sent,
            RequestStatus.matched,
            RequestStatus.closed,
            RequestStatus.cancelled,
        }
        assert VALID_TRANSITIONS[RequestStatus.in_progress] == expected

    def test_offer_sent_allowed_targets(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        expected = {
            RequestStatus.matched,
            RequestStatus.closed,
            RequestStatus.cancelled,
        }
        assert VALID_TRANSITIONS[RequestStatus.offer_sent] == expected

    def test_matched_can_only_go_to_closed(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert VALID_TRANSITIONS[RequestStatus.matched] == {RequestStatus.closed}

    def test_closed_has_no_transitions(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert VALID_TRANSITIONS[RequestStatus.closed] == set()

    def test_cancelled_has_no_transitions(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert VALID_TRANSITIONS[RequestStatus.cancelled] == set()

    def test_new_to_closed_is_rejected(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert RequestStatus.closed not in VALID_TRANSITIONS[RequestStatus.new]

    def test_in_progress_to_offer_sent_is_allowed(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import VALID_TRANSITIONS  # noqa: PLC0415

        assert RequestStatus.offer_sent in VALID_TRANSITIONS[RequestStatus.in_progress]


# ── create_request ─────────────────────────────────────────────────────────────

class TestCreateRequest:
    """create_request writes Request + history row, enqueues notify, never commits."""

    def test_create_request_adds_request_and_history_to_db(self):
        """create_request calls db.add() at least twice (Request + history row)."""
        from app.services import request_service  # noqa: PLC0415

        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        db.execute.return_value = mock_result

        client = _make_mock_client()
        data = _make_request_create()

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task:
            mock_task.apply_async = MagicMock()
            request_service.create_request(db=db, client=client, data=data)

        assert db.add.call_count >= 2

    def test_create_request_calls_flush_to_get_id(self):
        """create_request calls db.flush() (not db.commit()) to get the id."""
        from app.services import request_service  # noqa: PLC0415

        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        db.execute.return_value = mock_result

        client = _make_mock_client()
        data = _make_request_create()

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task:
            mock_task.apply_async = MagicMock()
            request_service.create_request(db=db, client=client, data=data)

        assert db.flush.called, "db.flush() should have been called"

    def test_create_request_never_commits(self):
        """create_request NEVER calls db.commit() — service-never-commits axiom."""
        from app.services import request_service  # noqa: PLC0415

        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        db.execute.return_value = mock_result

        client = _make_mock_client()
        data = _make_request_create()

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task:
            mock_task.apply_async = MagicMock()
            request_service.create_request(db=db, client=client, data=data)

        db.commit.assert_not_called()

    def test_create_request_enqueues_notify_task_with_queue(self):
        """create_request calls apply_async with queue='notify'."""
        from app.services import request_service  # noqa: PLC0415

        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        db.execute.return_value = mock_result

        client = _make_mock_client()
        data = _make_request_create()

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task:
            mock_task.apply_async = MagicMock()
            request_service.create_request(db=db, client=client, data=data)

            mock_task.apply_async.assert_called_once()
            call_kwargs = mock_task.apply_async.call_args
            # queue="notify" must be passed
            assert call_kwargs.kwargs.get("queue") == "notify", (
                f"Expected queue='notify' in apply_async call, got: {call_kwargs}"
            )


# ── transition_status ──────────────────────────────────────────────────────────

class TestTransitionStatus:
    """transition_status enforces the status machine, writes history, raises on invalid."""

    def test_invalid_transition_raises_value_error(self):
        """new → closed raises ValueError."""
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import transition_status  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request("new")

        with pytest.raises(ValueError):
            transition_status(db=db, request=req, to_status=RequestStatus.closed)

    def test_valid_transition_updates_status(self):
        """in_progress → offer_sent updates request.status."""
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import transition_status  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request("in_progress", id=10)

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task:
            mock_task.apply_async = MagicMock()
            result = transition_status(db=db, request=req, to_status=RequestStatus.offer_sent)

        assert req.status == RequestStatus.offer_sent
        assert result is req

    def test_valid_transition_writes_history_row(self):
        """transition_status adds a RequestStatusHistory row."""
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import transition_status  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request("in_progress", id=10)

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task:
            mock_task.apply_async = MagicMock()
            transition_status(db=db, request=req, to_status=RequestStatus.matched)

        assert db.add.called

    def test_transition_enqueues_notify(self):
        """transition_status enqueues send_status_change_notification."""
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import transition_status  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request("in_progress", id=10)

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task:
            mock_task.apply_async = MagicMock()
            transition_status(db=db, request=req, to_status=RequestStatus.offer_sent)

            mock_task.apply_async.assert_called_once()

    def test_transition_writes_audit_when_changed_by_staff(self):
        """transition_status writes audit_log when changed_by is set."""
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import transition_status  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request("in_progress", id=10)

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task, \
             patch("app.services.request_service.write_audit") as mock_audit:
            mock_task.apply_async = MagicMock()
            transition_status(db=db, request=req, to_status=RequestStatus.offer_sent, changed_by=5)

            mock_audit.assert_called_once()
            call_args_str = str(mock_audit.call_args)
            assert "request.status_change" in call_args_str

    def test_transition_no_audit_when_changed_by_none(self):
        """transition_status does NOT write audit when changed_by is None."""
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import transition_status  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request("in_progress", id=10)

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task, \
             patch("app.services.request_service.write_audit") as mock_audit:
            mock_task.apply_async = MagicMock()
            transition_status(db=db, request=req, to_status=RequestStatus.offer_sent, changed_by=None)

            mock_audit.assert_not_called()

    def test_transition_never_commits(self):
        """transition_status never calls db.commit()."""
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import transition_status  # noqa: PLC0415

        db = _make_mock_db()
        req = _make_mock_request("in_progress", id=10)

        with patch("app.tasks.notify.send_status_change_notification", create=True) as mock_task:
            mock_task.apply_async = MagicMock()
            transition_status(db=db, request=req, to_status=RequestStatus.offer_sent)

        db.commit.assert_not_called()


# ── client_facing_status ───────────────────────────────────────────────────────

class TestClientFacingStatus:
    """client_facing_status maps all 7 RequestStatus values to D-10 keys."""

    def test_new_maps_to_new(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import client_facing_status  # noqa: PLC0415
        assert client_facing_status(RequestStatus.new) == "new"

    def test_viewed_maps_to_in_review(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import client_facing_status  # noqa: PLC0415
        assert client_facing_status(RequestStatus.viewed) == "in_review"

    def test_in_progress_maps_to_in_review(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import client_facing_status  # noqa: PLC0415
        assert client_facing_status(RequestStatus.in_progress) == "in_review"

    def test_offer_sent_maps_to_offer_received(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import client_facing_status  # noqa: PLC0415
        assert client_facing_status(RequestStatus.offer_sent) == "offer_received"

    def test_matched_maps_to_matched(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import client_facing_status  # noqa: PLC0415
        assert client_facing_status(RequestStatus.matched) == "matched"

    def test_closed_maps_to_closed(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import client_facing_status  # noqa: PLC0415
        assert client_facing_status(RequestStatus.closed) == "closed"

    def test_cancelled_maps_to_cancelled(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import client_facing_status  # noqa: PLC0415
        assert client_facing_status(RequestStatus.cancelled) == "cancelled"


# ── CLIENT_STATUS_MAP ──────────────────────────────────────────────────────────

class TestClientStatusMap:
    """CLIENT_STATUS_MAP dict contains entries for all 7 RequestStatus values."""

    def test_client_status_map_has_all_statuses(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import CLIENT_STATUS_MAP  # noqa: PLC0415

        for status in RequestStatus:
            assert status in CLIENT_STATUS_MAP, f"Status {status} missing from CLIENT_STATUS_MAP"

    def test_client_status_map_contains_expected_keys(self):
        from app.models.enums import RequestStatus  # noqa: PLC0415
        from app.services.request_service import CLIENT_STATUS_MAP  # noqa: PLC0415

        assert CLIENT_STATUS_MAP[RequestStatus.new] == "new"
        assert CLIENT_STATUS_MAP[RequestStatus.viewed] == "in_review"
        assert CLIENT_STATUS_MAP[RequestStatus.in_progress] == "in_review"
        assert CLIENT_STATUS_MAP[RequestStatus.offer_sent] == "offer_received"
        assert CLIENT_STATUS_MAP[RequestStatus.matched] == "matched"
        assert CLIENT_STATUS_MAP[RequestStatus.closed] == "closed"
        assert CLIENT_STATUS_MAP[RequestStatus.cancelled] == "cancelled"
