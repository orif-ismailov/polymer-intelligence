"""DB-integration tests (idempotency, checkpoint, retry set, labels).

Skipped unless ``UZEX_BACKFILL_TEST_DSN`` points at a reachable Postgres. Uses a
dedicated throwaway source name and cleans up after itself, so it never touches
real backfill rows.
"""

from __future__ import annotations

import os

import pytest
from uzex_backfill import db
from uzex_backfill.parser import hash_fields, status_sentinel_hash

_DSN = os.environ.get("UZEX_BACKFILL_TEST_DSN")
pytestmark = pytest.mark.skipif(not _DSN, reason="UZEX_BACKFILL_TEST_DSN not set")

_SOURCE = "pytest_uzex_backfill"
# Synthetic label names so cleanup never touches real discovered labels.
_LBL = ("pytest_lbl_a", "pytest_lbl_b", "pytest_lbl_c")


@pytest.fixture
def conn():
    connection = db.connect(_DSN)
    db.apply_schema(connection)
    _cleanup(connection)
    yield connection
    _cleanup(connection)
    connection.close()


def _cleanup(connection):
    with connection.cursor() as cur:
        cur.execute("DELETE FROM uzex_raw_offers WHERE source = %s", (_SOURCE,))
        cur.execute("DELETE FROM uzex_backfill_progress WHERE worker_name = %s", (_SOURCE,))
        cur.execute("DELETE FROM uzex_discovered_labels WHERE label = ANY(%s)", (list(_LBL),))
    connection.commit()


def _count(connection, external_id):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM uzex_raw_offers WHERE source = %s AND external_id = %s",
            (_SOURCE, external_id),
        )
        return cur.fetchone()[0]


def _upsert(connection, external_id, status, fields, content_hash):
    return db.upsert_offer(
        connection,
        source=_SOURCE,
        external_id=external_id,
        http_status=200,
        final_url=f"https://uzex.uz/trade/offer/{external_id}",
        status=status,
        fields=fields,
        raw_html=None,
        content_hash=content_hash,
    )


def test_reinsert_same_content_is_noop(conn):
    fields = {"Наименование": "тест"}
    h = hash_fields(fields)
    assert _upsert(conn, 1, "ok", fields, h) is True
    assert _upsert(conn, 1, "ok", fields, h) is False  # duplicate
    assert _count(conn, 1) == 1


def test_changed_content_adds_revision(conn):
    f1 = {"Цена": "100"}
    f2 = {"Цена": "200"}
    assert _upsert(conn, 2, "ok", f1, hash_fields(f1)) is True
    assert _upsert(conn, 2, "ok", f2, hash_fields(f2)) is True  # new revision
    assert _count(conn, 2) == 2


def test_repeated_not_found_is_noop(conn):
    sentinel = status_sentinel_hash("not_found")
    assert _upsert(conn, 3, "not_found", None, sentinel) is True
    assert _upsert(conn, 3, "not_found", None, sentinel) is False
    assert _count(conn, 3) == 1


def test_checkpoint_is_monotonic(conn):
    db.write_checkpoint(conn, _SOURCE, 500)
    assert db.get_checkpoint(conn, _SOURCE) == 500
    db.write_checkpoint(conn, _SOURCE, 400)  # a lower value must not regress
    assert db.get_checkpoint(conn, _SOURCE) == 500
    db.write_checkpoint(conn, _SOURCE, 600)
    assert db.get_checkpoint(conn, _SOURCE) == 600


def test_failed_ids_exclude_those_with_ok_revision(conn):
    _upsert(conn, 10, "fetch_failed", None, status_sentinel_hash("fetch_failed"))
    _upsert(conn, 11, "fetch_failed", None, status_sentinel_hash("fetch_failed"))
    # id 10 later succeeds -> should drop out of the retry set
    _upsert(conn, 10, "ok", {"x": "1"}, hash_fields({"x": "1"}))
    assert db.failed_external_ids(conn, _SOURCE) == [11]


def test_labels_upsert_idempotent(conn):
    a, b, c = _LBL
    db.insert_labels(conn, {a: 1, b: 1})
    db.insert_labels(conn, {a: 2, c: 5})  # `a` already known
    known = db.load_known_labels(conn)
    assert {a, b, c} <= known
    with conn.cursor() as cur:
        cur.execute("SELECT first_seen_id FROM uzex_discovered_labels WHERE label = %s", (a,))
        assert cur.fetchone()[0] == 1  # first-seen id preserved
