"""`app.core.numbering` — the shared per-period reference-number counter.

Six domains used to carry their own copy of this. The copies agreed on the
mechanism and disagreed on the advisory-lock key, which each file picked by hand
(`+1`, `+34_000`, `+35_000`, `+39_000`) with no shared registry.

The behavioural change worth pinning is the lock. `pg_advisory_xact_lock` is held
until COMMIT, and the old code took it on EVERY call — so concurrent creations in
a domain serialised for the whole length of their transactions, capping
throughput at one per transaction rather than one per `nextval`. It is now taken
only when the sequence is genuinely missing. These tests assert exactly that,
since it is invisible in the returned value and a future "simplification" could
quietly put it back.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core import numbering


def _db(*, sequence_exists: bool, nextval: int = 7) -> tuple[MagicMock, list[str]]:
    """Mock session recording the SQL it is asked to run."""
    db = MagicMock()
    statements: list[str] = []

    def _execute(stmt: Any, *_a: Any, **_k: Any) -> MagicMock:
        sql = " ".join(str(stmt).split())
        statements.append(sql)
        result = MagicMock()
        if "to_regclass" in sql:
            result.scalar.return_value = "deal_seq_2026" if sequence_exists else None
        elif "nextval" in sql:
            result.scalar.return_value = nextval
        else:
            result.scalar.return_value = None
        return result

    db.execute.side_effect = _execute
    return db, statements


def test_existing_sequence_takes_no_lock_and_no_ddl() -> None:
    """The hot path is a probe and a nextval — nothing else.

    This is the fix. A lock here is held to commit, so taking one per call
    serialises every concurrent creation in the domain for the duration of its
    whole transaction.
    """
    db, statements = _db(sequence_exists=True)

    assert numbering.next_in_sequence(db, "deal_seq_2026", 2026) == 7

    joined = " | ".join(statements)
    assert "pg_advisory_xact_lock" not in joined, f"took a lock on the hot path: {joined}"
    assert "CREATE SEQUENCE" not in joined, f"ran DDL on the hot path: {joined}"
    assert any("nextval" in s for s in statements)


def test_missing_sequence_locks_then_creates() -> None:
    """First use of a period still serialises: that race is real.

    Two simultaneous first-callers otherwise collide in the catalog and one gets
    "tuple concurrently updated", surfacing as a 500 on whichever request lost.
    """
    db, statements = _db(sequence_exists=False)

    assert numbering.next_in_sequence(db, "deal_seq_2026", 2026) == 7

    joined = " | ".join(statements)
    assert "pg_advisory_xact_lock" in joined
    assert "CREATE SEQUENCE IF NOT EXISTS deal_seq_2026" in joined
    # Order matters: the lock must precede the create, or it guards nothing.
    lock_at = next(i for i, s in enumerate(statements) if "pg_advisory_xact_lock" in s)
    create_at = next(i for i, s in enumerate(statements) if "CREATE SEQUENCE" in s)
    assert lock_at < create_at


def test_sequence_name_is_bound_not_interpolated_into_nextval() -> None:
    """`nextval` takes the name as a parameter, so it is never a SQL literal."""
    db, statements = _db(sequence_exists=True)

    numbering.next_in_sequence(db, "deal_seq_2026", 2026)

    nextval_sql = next(s for s in statements if "nextval" in s)
    assert "CAST(:name AS regclass)" in nextval_sql
    assert "deal_seq_2026" not in nextval_sql


@pytest.mark.parametrize(
    "bad",
    [
        "deal_seq_2026; DROP TABLE deals",
        "Deal_Seq_2026",  # uppercase — not a name this codebase generates
        "2026_seq",  # leading digit
        "",
        "x" * 64,  # over the identifier budget
    ],
)
def test_unsafe_sequence_names_are_rejected(bad: str) -> None:
    """CREATE SEQUENCE cannot take a bound parameter, so the name is validated.

    Every caller derives the name server-side, so reaching this is a programming
    error rather than an attack — but it is the one value that still lands in DDL
    as a literal, and that is worth a guard rather than a comment.
    """
    db, _ = _db(sequence_exists=False)
    with pytest.raises(ValueError, match="unsafe sequence name"):
        numbering.next_in_sequence(db, bad, 2026)


def test_lock_bases_are_distinct() -> None:
    """No two yearly namespaces may share a key.

    The old per-file constants were chosen by hand and justified in comments in
    two of the six files. Collisions would not corrupt anything — the lock only
    guards a first create — but they would serialise unrelated domains against
    each other, which is precisely what those comments were trying to avoid.
    """
    yearly = [
        numbering.LOCK_BASE_DEAL,
        numbering.LOCK_BASE_LAB_ORDER,
        numbering.LOCK_BASE_FACTORY_RFQ,
        numbering.LOCK_BASE_LOGISTICS_REQUEST,
        numbering.LOCK_BASE_LAB_REQUEST,
    ]
    assert len(set(yearly)) == len(yearly)
    # Keys are base + year, so bases must be further apart than the span of years
    # the platform could plausibly run for.
    assert min(abs(a - b) for a in yearly for b in yearly if a != b) > 500
