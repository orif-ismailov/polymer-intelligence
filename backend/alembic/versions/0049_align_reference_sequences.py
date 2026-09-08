"""Repair reference-number sequences left behind by the demo seeders.

Six domains hand out reference numbers (`DEAL-2026-000001`, `LAB-…`, `REQ-…`,
`LBR-…`, `FRQ-…`, `LRQ-…`) from Postgres sequences via
`app.core.numbering.next_in_sequence`. The showcase seeders never called those
generators — they INSERT the number as a literal, counting from 1 — and
`seed_showcase.purge()` DROPPED the sequences on top of that, so numbering
"restarted with the data". It restarted ON the data.

The consequence, on every seeded deployment: the first REAL deal drew
`nextval` = 1, built `DEAL-2026-000001`, and hit `uq_deals_number`. A buyer
accepting a supplier's quote — the single step that turns a tender into a deal —
got a 500, the tender stayed open, and the whole deal → contract → signing chain
behind it was unreachable. `nextval` then walked 2, 3, 4 … through numbers the
seeder had already taken, so it reproduced every time.

`app/seed/align_numbering.py` fixes the seeders going forward. This migration
fixes the databases they already seeded, which no code change can reach.

Idempotent and safe on a clean install: it only ever moves a sequence FORWARD,
to the highest ordinal actually present in the table, and does nothing at all
where the table is empty or the sequence is already ahead (the normal case, and
the only case on production).

Revision ID: 0049
Revises: 0048
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


#: (table, number prefix, sequence stem) — the yearly families,
#: `<PREFIX>-YYYY-NNNNNN` drawn from `<stem>_YYYY`. Mirrors `_YEARLY` in
#: `app/seed/align_numbering.py`; a test asserts the two agree.
_YEARLY: tuple[tuple[str, str, str], ...] = (
    ("deals", "DEAL", "deal_seq"),
    ("lab_orders", "LAB", "lab_order_seq"),
    ("lab_requests", "LBR", "lab_request_seq"),
    ("factory_rfqs", "FRQ", "factory_rfq_seq"),
    ("logistics_requests", "LRQ", "logistics_request_seq"),
)


def _align(bind: sa.engine.Connection, sequence: str, last_used: int) -> None:
    """Move `sequence` forward to `last_used`; never backward."""
    bind.execute(sa.text(f'CREATE SEQUENCE IF NOT EXISTS "{sequence}"'))
    row = bind.execute(
        sa.text(
            "SELECT last_value FROM pg_sequences "
            "WHERE schemaname = current_schema() AND sequencename = :name"
        ),
        {"name": sequence},
    ).first()
    current = int(row[0]) if row is not None and row[0] is not None else 0
    if last_used > current:
        bind.execute(
            sa.text("SELECT setval(CAST(:name AS regclass), CAST(:last AS bigint), true)"),
            {"name": sequence, "last": last_used},
        )


def upgrade() -> None:
    bind = op.get_bind()

    for table, prefix, stem in _YEARLY:
        rows = bind.execute(
            sa.text(
                f"""
                SELECT split_part(number, '-', 2)                      AS period,
                       MAX(CAST(split_part(number, '-', 3) AS bigint)) AS last_used
                  FROM {table}
                 WHERE number ~ :pattern
                 GROUP BY 1
                """  # noqa: S608 — table names are the fixed literals above
            ),
            {"pattern": f"^{prefix}-[0-9]{{4}}-[0-9]+$"},
        ).all()
        for period, last_used in rows:
            _align(bind, f"{stem}_{period}", int(last_used))

    # `requests` is numbered per DAY: REQ-YYYY-MM-DD-NNNNN from req_seq_YYYYMMDD.
    rows = bind.execute(
        sa.text(
            """
            SELECT replace(substring(number FROM 5 FOR 10), '-', '') AS period,
                   MAX(CAST(split_part(number, '-', 5) AS bigint))   AS last_used
              FROM requests
             WHERE number ~ '^REQ-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]+$'
             GROUP BY 1
            """
        )
    ).all()
    for period, last_used in rows:
        _align(bind, f"req_seq_{period}", int(last_used))


def downgrade() -> None:
    """No-op.

    A sequence position is not schema, and rewinding one would hand out a number
    that is already on a row — the exact failure this migration exists to end.
    """
