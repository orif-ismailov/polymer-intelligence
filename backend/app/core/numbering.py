"""Per-period reference numbers (REQ-…, DEAL-…, LAB-…) from Postgres sequences.

Six domains hand out human-facing reference numbers that reset each period —
`REQ-2026-06-16-00001`, `DEAL-2026-000123`, and so on. Each one had its own copy
of the same eleven lines, and the copies had drifted: five keyed their advisory
lock on the year plus a different hand-picked constant (`+1`, `+34_000`,
`+35_000`, `+39_000`), chosen by whoever wrote the file, recorded nowhere
central. `logistics` even carries a comment explaining why it picked 35_000
rather than reusing 34_000 — the collision hazard was already visible to
somebody. Nothing but luck stopped the seventh domain from picking a key in use.

Lives in `app/core/` rather than `app/services/`: the shared-kernel list there is
closed to business logic, and this is a database primitive, a sibling of `db.py`.

WHAT CHANGED BEYOND DEDUPLICATION
---------------------------------
The old shape took `pg_advisory_xact_lock` on EVERY call:

    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": int(year)})
    db.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq}"))
    nextval  = db.execute(text(f"SELECT nextval('{seq}')")).scalar()

`pg_advisory_xact_lock` is held until COMMIT, not until the next statement. So
every concurrent deal creation serialised on one lock for the whole duration of
its transaction, and throughput was capped at one per transaction rather than
one per `nextval`. The comments only ever justified the FIRST create of the
period — that is the operation that genuinely races — but the code paid the cost
forever after.

So the lock is now taken only when the sequence is actually missing, decided by
a `to_regclass` probe, which is a catalog lookup taking no lock at all. In the
overwhelmingly common case (sequence exists) the call is a bare `nextval`, which
is already atomic and needs no help. The race the lock exists for is unchanged:
two callers can both see NULL, and the loser serialises behind the winner and
finds `IF NOT EXISTS` already satisfied.

`nextval` also takes the name as a BOUND PARAMETER cast to `regclass`, so the
sequence name no longer reaches SQL as a literal. Only `CREATE SEQUENCE` still
interpolates, because Postgres has no parameterised DDL — hence the one
remaining validation + suppression here rather than six spread across domains.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from sqlalchemy.orm import Session

#: Advisory-lock keys, one namespace per caller, ALL IN ONE PLACE.
#:
#: The key is `base + period`, where period is the year (or YYYYMMDD for the
#: daily one). Bases are spaced far enough apart that no two callers can collide
#: for any plausible period: the daily key is a full YYYYMMDD (~2 x 10^7) and
#: sits above every yearly base by construction.
#:
#: Only ever used to serialise the first CREATE SEQUENCE of a period, so a
#: collision would cost one serialised statement rather than corrupt anything —
#: but a collision is still a real contention bug, and the previous arrangement
#: made one a matter of time.
LOCK_BASE_DEAL = 0
LOCK_BASE_LAB_ORDER = 1_000
LOCK_BASE_FACTORY_RFQ = 34_000
LOCK_BASE_LOGISTICS_REQUEST = 35_000
LOCK_BASE_LAB_REQUEST = 39_000
#: The daily request counter keys on YYYYMMDD directly — see `generate_request_number`.
LOCK_BASE_REQUEST = 0

#: A sequence name is server-derived, never user input. Validated anyway, because
#: it is the one value that still reaches DDL as a literal.
_SAFE_SEQUENCE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def next_in_sequence(db: Session, sequence: str, lock_key: int) -> int:
    """Return the next value of `sequence`, creating it on genuine first use.

    Args:
        db: Active session. The value is drawn in the caller's transaction, so it
            is rolled back with everything else if the caller aborts — reference
            numbers may therefore have gaps, which they always could (`nextval`
            is non-transactional by design).
        sequence: Sequence name, e.g. `deal_seq_2026`. Must be a lowercase
            identifier; anything else is a programming error and raises.
        lock_key: Advisory-lock key for the create-on-first-use race. Use one of
            the `LOCK_BASE_*` constants above plus the period.

    Raises:
        ValueError: if `sequence` is not a plain lowercase identifier.
    """
    if not _SAFE_SEQUENCE_NAME.match(sequence):
        raise ValueError(f"unsafe sequence name: {sequence!r}")

    # Catalog probe, no lock. NULL means "not created yet" — the only case that
    # needs serialising. Everything else goes straight to nextval.
    exists = db.execute(sa.text("SELECT to_regclass(:name)"), {"name": sequence}).scalar()
    if exists is None:
        # `CREATE SEQUENCE IF NOT EXISTS` is NOT concurrency safe for the first
        # create: two simultaneous callers race on the catalog and one errors
        # with "tuple concurrently updated", surfacing as a 500 on whichever
        # request lost. The lock makes that first create single-file.
        db.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})
        db.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {sequence}"))  # noqa: S608 — validated above

    # Bound parameter cast to regclass: the name never appears as a SQL literal.
    # (`CAST(:x AS regclass)`, not `:x::regclass` — the latter breaks SQLAlchemy's
    # bind-parameter parsing.)
    value = db.execute(
        sa.text("SELECT nextval(CAST(:name AS regclass))"), {"name": sequence}
    ).scalar()
    if value is None:  # pragma: no cover — nextval never returns NULL
        raise RuntimeError(f"nextval returned NULL for {sequence!r}")
    return int(value)
