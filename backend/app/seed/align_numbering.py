"""Point the reference-number sequences past the rows a seeder just wrote.

WHY THIS EXISTS
---------------
Six domains hand out human-facing reference numbers from Postgres sequences
(`DEAL-2026-000001`, `LAB-2026-000001`, `REQ-2026-09-08-00001`, …) through
`app.core.numbering.next_in_sequence`. The demo seeders do not call those
generators: they INSERT the number as a literal with raw SQL, counting from 1.
So the sequence knows nothing about the rows, and `seed_showcase.purge()` then
DROPS it as well — deliberately, so that "numbering restarts with the data".

It restarted ON TOP of the data. After a showcase seed the first REAL deal drew
`nextval` = 1, built `DEAL-2026-000001` — a number the seeder had just written —
and died on `uq_deals_number`. What a user saw was a **500 on accepting a
supplier's quote**, the one step that turns a tender into a deal: the tender
stayed open, no deal was created, and every screen behind it (deal room, chat,
contract, signing) was unreachable. It reproduced every time, because `nextval`
kept walking 1, 2, 3 … through numbers the seeder had already taken. Only a
seeded deployment could hit it, which is why no test and no local run ever did.

Restarting the numbering means starting AFTER the demo rows, not on top of them.

HOW
---
Called at the end of every seeder that writes a reference number. The value is
derived from the TABLE, never from the seeder's own counters — a seeder adding
rows to a database another seeder already filled then still leaves the sequence
past both, and `align_sequence` refuses to move one backwards.

Only the app's OWN prefix is scanned per table. `seed_demo` writes `REQ-DEMO-…`
and `seed_showcase_profiles` writes `LOG-…` where the app generates `LRQ-…`:
different namespaces, unreachable by `nextval`, and therefore not our business.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.numbering import align_sequence

#: Yearly families: `<PREFIX>-YYYY-NNNNNN` drawn from `<stem>_YYYY`.
#: Keep in step with the `generate_*_number` function named beside each row —
#: the prefix and the sequence stem are one contract, split across two files.
_YEARLY: tuple[tuple[str, str, str], ...] = (
    ("deals", "DEAL", "deal_seq"),                          # deals.service
    ("lab_orders", "LAB", "lab_order_seq"),                 # lab_orders.service
    ("lab_requests", "LBR", "lab_request_seq"),             # laboratory.service
    ("factory_rfqs", "FRQ", "factory_rfq_seq"),             # manufacturers.service
    ("logistics_requests", "LRQ", "logistics_request_seq"),  # logistics.service
)

#: `requests` is the odd one: `REQ-YYYY-MM-DD-NNNNN`, drawn from a DAILY
#: sequence `req_seq_YYYYMMDD` (see `requests.service.generate_request_number`).
#: One seeded day = one sequence to align, so this is a GROUP BY, not a max.
_REQUEST_PERIODS = sa.text(
    """
    SELECT replace(substring(number FROM 5 FOR 10), '-', '') AS period,
           MAX(CAST(split_part(number, '-', 5) AS bigint))   AS last_used
      FROM requests
     WHERE number ~ '^REQ-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]+$'
     GROUP BY 1
    """
)


def align_reference_numbers(db: Session) -> dict[str, int]:
    """Advance every reference-number sequence past the rows now in the tables.

    Flush-only — the caller commits. Returns `{sequence: last_used}` for the
    sequences that were moved, so a seeder can print what it did.
    """
    moved: dict[str, int] = {}

    for table, prefix, stem in _YEARLY:
        rows = db.execute(
            sa.text(
                f"""
                SELECT split_part(number, '-', 2)                    AS period,
                       MAX(CAST(split_part(number, '-', 3) AS bigint)) AS last_used
                  FROM {table}
                 WHERE number ~ :pattern
                 GROUP BY 1
                """  # noqa: S608 — table names are the fixed literals above
            ),
            {"pattern": f"^{prefix}-[0-9]{{4}}-[0-9]+$"},
        ).all()
        for period, last_used in rows:
            sequence = f"{stem}_{period}"
            align_sequence(db, sequence, int(last_used))
            moved[sequence] = int(last_used)

    for period, last_used in db.execute(_REQUEST_PERIODS).all():
        sequence = f"req_seq_{period}"
        align_sequence(db, sequence, int(last_used))
        moved[sequence] = int(last_used)

    db.flush()
    return moved
