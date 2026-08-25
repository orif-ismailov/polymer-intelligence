"""`poll_didox_documents` (P7.a Stage 2 — W10).

There are no partner webhooks, so this beat is the only way we learn that a
counterparty signed or that the tax committee annulled a document. Everything
asserted here is a rule that fails quietly if it is wrong:

  * the mode gate runs BEFORE any I/O — polling a stub rail would be a
    conversation with nobody;
  * it never raises, because a beat that raises just retries the same failure;
  * a company with no cached `user-key` is SKIPPED, not an error: we cannot mint
    one for them, and the user brings one the next time they act;
  * one bad row does not stop the sweep;
  * the cursor is written BEHIND now, on purpose — `dateFromUpdated` is
    day-granular, so pages must be allowed to repeat.
"""

from __future__ import annotations

import datetime

from app.tasks import edi as edi_tasks


class _Doc:
    def __init__(self, doc_id: int = 1, *, status: int = 1, company_id: int = 7) -> None:
        self.id = doc_id
        self.didox_id = f"hex{doc_id}"
        self.status = status
        self.status_synced_at = None
        self.owner_company_id = company_id
        self.doc_type = "007"
        self.subject_kind = "contract"
        self.subject_id = 99
        self.number = f"C-{doc_id}"
        self.provider_archive_path = None
        self.provider_archive_sha256 = None
        self.archived_at = None
        self.last_error = None


class _Record:
    def __init__(self, tin: str = "590640341") -> None:
        self.tin = tin
        self.last_polled_at = None


class TestModeGate:
    def test_the_stub_rail_is_reported_not_polled(self, monkeypatch) -> None:  # noqa: ANN001
        """A stub standing in for an EDI operator is exactly the confusion this
        rail must not create — so it says which rail it is on."""
        from app.domains.edi import onboarding

        monkeypatch.setattr(onboarding.settings_service, "get", lambda db, key: "stub")

        called: list[str] = []
        monkeypatch.setattr(edi_tasks, "_poll", lambda db, limit: called.append("polled"))

        # `Session(engine)` is the only thing between us and the gate; the gate is
        # checked first, so a stub never reaches the query.
        class _Session:
            def __init__(self, *a: object, **k: object) -> None: ...
            def __enter__(self):  # noqa: ANN202
                return self
            def __exit__(self, *a: object) -> None: ...
            def commit(self) -> None: ...

        monkeypatch.setattr("sqlalchemy.orm.Session", _Session)
        out = edi_tasks.poll_didox_documents()

        assert out["status"] == "disabled"
        assert called == []


class TestNeverRaises:
    def test_an_exception_becomes_a_report(self, monkeypatch) -> None:  # noqa: ANN001
        """A beat that raises just retries the same failure on the next tick."""

        def _boom(*a: object, **k: object) -> None:
            raise RuntimeError("database on fire")

        monkeypatch.setattr("sqlalchemy.orm.Session", _boom)
        out = edi_tasks.poll_didox_documents()

        assert out["status"] == "error"
        assert "database on fire" in out["error"]


class TestSweep:
    """`_poll` drives the whole sweep; a fake db/client keeps it honest."""

    class _Query:
        def __init__(self, rows: list[_Doc]) -> None:
            self.rows = rows

        def filter(self, *a: object) -> TestSweep._Query:
            return self

        def order_by(self, *a: object) -> TestSweep._Query:
            return self

        def limit(self, n: int) -> TestSweep._Query:
            return self

        def all(self) -> list[_Doc]:
            return self.rows

    class _Db:
        def __init__(self, rows: list[_Doc], record: _Record | None) -> None:
            self.rows = rows
            self.record = record

        def query(self, model: object) -> TestSweep._Query:
            return TestSweep._Query(self.rows)

        def get(self, model: object, pk: object) -> _Record | None:
            return self.record

        def flush(self) -> None: ...

    class _View:
        def __init__(self, status: int) -> None:
            self.status = status
            self.json_payload: dict[str, object] = {}
            self.to_sign = None
            self.raw: dict[str, object] = {}

    class _Client:
        def __init__(self, status: int = 3, fail_on: int | None = None) -> None:
            self.status = status
            self.fail_on = fail_on
            self.seen: list[str] = []

        def get_document(self, didox_id: str, *, owner: int = 1, user_key: str | None = None):  # noqa: ANN202
            self.seen.append(didox_id)
            if self.fail_on is not None and didox_id == f"hex{self.fail_on}":
                raise RuntimeError("one bad row")
            return TestSweep._View(self.status)

    def _run(self, monkeypatch, rows, record, client, *, key="k"):  # noqa: ANN001, ANN202
        monkeypatch.setattr(edi_tasks, "_redis", lambda: object())
        monkeypatch.setattr(
            "app.domains.edi.session.cached_user_key", lambda r, tin: key
        )
        monkeypatch.setattr(
            "app.integrations.didox.get_didox_client", lambda: client
        )
        applied: list[int] = []

        def _apply(db, row, status, *, user_key, client):  # noqa: ANN001, ANN202
            applied.append(status)
            row.status = status
            return status == 3

        monkeypatch.setattr("app.domains.edi.service.apply_status", _apply)
        return edi_tasks._poll(TestSweep._Db(rows, record), limit=100), applied

    def test_a_company_without_a_key_is_skipped_not_failed(self, monkeypatch) -> None:  # noqa: ANN001
        """We cannot mint this key ourselves — the user brings one when they act."""
        report, applied = self._run(
            monkeypatch, [_Doc(1)], _Record(), TestSweep._Client(), key=None
        )
        assert report["skipped_no_key"] == 1
        assert report["checked"] == 0
        assert applied == []

    def test_a_signed_document_counts_as_activated(self, monkeypatch) -> None:  # noqa: ANN001
        report, applied = self._run(monkeypatch, [_Doc(1)], _Record(), TestSweep._Client(status=3))
        assert applied == [3]
        assert report["checked"] == 1
        assert report["activated"] == 1

    def test_one_bad_row_does_not_stop_the_sweep(self, monkeypatch) -> None:  # noqa: ANN001
        rows = [_Doc(1), _Doc(2), _Doc(3)]
        client = TestSweep._Client(status=3, fail_on=2)
        report, applied = self._run(monkeypatch, rows, _Record(), client)

        assert client.seen == ["hex1", "hex2", "hex3"]
        assert report["checked"] == 3
        assert applied == [3, 3]          # the failing row applied nothing
        assert rows[1].last_error == "one bad row"

    def test_terminal_statuses_are_alerted_and_not_acted_on(self, monkeypatch) -> None:  # noqa: ANN001
        """`4` and `50` are legal events for a person. `active` is terminal and a
        deal may already be riding on it."""
        report, _ = self._run(monkeypatch, [_Doc(1)], _Record(), TestSweep._Client(status=50))

        assert report["activated"] == 0
        assert [a["status"] for a in report["alerts"]] == [50]

    def test_the_cursor_is_written_behind_now(self, monkeypatch) -> None:  # noqa: ANN001
        """`dateFromUpdated` is DAY-granular, so the window must overlap — which
        is safe only because `apply_status` is forward-only."""
        record = _Record()
        before = datetime.datetime.now(datetime.UTC)
        self._run(monkeypatch, [_Doc(1)], record, TestSweep._Client())

        assert record.last_polled_at is not None
        assert record.last_polled_at < before
        assert (before - record.last_polled_at) >= datetime.timedelta(hours=23)

    def test_nothing_live_is_a_clean_no_op(self, monkeypatch) -> None:  # noqa: ANN001
        report, applied = self._run(monkeypatch, [], _Record(), TestSweep._Client())
        assert report == {
            "checked": 0, "advanced": 0, "activated": 0, "skipped_no_key": 0, "alerts": []
        }
        assert applied == []


def test_the_beat_and_the_task_module_are_registered() -> None:
    """Autodiscover is a no-op here — an unlisted module is an unregistered task."""
    from app.tasks.celery_app import _TASK_MODULES
    from app.tasks.schedule import BEAT_SCHEDULE

    assert "app.tasks.edi" in _TASK_MODULES
    assert BEAT_SCHEDULE["poll_didox_documents"]["task"] == "poll_didox_documents"


def test_the_admin_routes_are_mounted() -> None:
    from app.main import create_app

    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/admin/didox/documents" in paths
    assert "/api/v1/admin/didox/companies" in paths
