"""Backfill the tenders that were left open by the pre-IMEX-6 accept path.

Choosing a winner has always opened the deal, but until `af96c56` it never moved
the REQUEST. So a tender with an accepted quote and a live deal hanging off it
still read `new`, and its timeline held only the row it was created with — the
buyer's main workspace showed every such tender as if nobody had answered it.
That is the symptom QA reported (IMEX-6).

The code fix governs transitions made from now on and cannot reach rows already
written. This migration reaches them, and only them:

    an accepted `rfq_responses` row  AND  a `deals` row for the same request
    AND  the request is still in a status from which `matched` is legal

The last clause is what keeps this honest. A `cancelled` or `closed` tender is
NOT touched even when it has an accepted quote and a deal — that combination is
Finding 1 (a deal opened against a cancelled tender, now refused with 409), and
"repair" there would mean overwriting a cancellation somebody meant. Those rows
stay visibly odd, which is the correct outcome for data that recorded something
that should never have happened.

Timestamps are NOT invented. The `offer_sent` row is stamped with the accepted
quote's `created_at` and the `matched` row with the deal's, both of which are
real recorded times. `changed_by` is NULL, matching what the live path writes:
the buyer is not staff, and that column is a `staff_users` FK.

No notifications are emitted. These transitions happened months ago in every
sense except the database's; telling a buyer "your tender has a match" now would
be a lie about when.

Revision ID: 0050
Revises: 0049
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


#: Statuses from which `matched` is a legal move — mirrors the `matched` edges in
#: `request_service.VALID_TRANSITIONS`. Deliberately excludes `matched` itself
#: (nothing to do), `closed` and `cancelled` (see the module docstring).
_OPEN = ("new", "viewed", "in_progress", "offer_sent")

#: Of those, the ones that have not yet passed through `offer_sent`, and so need
#: that row written before the `matched` one. `offer_sent -> matched` is a single
#: step and needs only the second.
_PRE_OFFER_SENT = ("new", "viewed", "in_progress")


#: The affected rows, with the two real timestamps the history rows are stamped
#: with. `MIN(...)` over the accepted quote is a formality — `open_deal_from_response`
#: allows exactly one accepted response per request — but it keeps the row count
#: right if a database somehow holds two.
_AFFECTED = sa.text(
    """
    SELECT r.id                     AS request_id,
           r.status::text           AS status,
           MIN(q.created_at)        AS quoted_at,
           MIN(d.created_at)        AS dealt_at
      FROM requests r
      JOIN rfq_responses q ON q.request_id = r.id AND q.status = 'accepted'
      JOIN deals        d ON d.request_id = r.id
     WHERE r.status::text = ANY(:open_statuses)
     GROUP BY r.id, r.status
     ORDER BY r.id
    """
)


def upgrade() -> None:
    backfill(op.get_bind())


def backfill(bind: sa.engine.Connection) -> int:
    """Apply the backfill on `bind`; return how many tenders were repaired.

    Split out of `upgrade()` so a real-Postgres test can build the pre-fix state
    and run the real statements against it. A data migration whose only test is
    "the file parses and the revision is 0050" proves nothing about the WHERE
    clause, which is the whole of the risk here.
    """
    rows = bind.execute(_AFFECTED, {"open_statuses": list(_OPEN)}).all()
    if not rows:
        return 0

    for request_id, status, quoted_at, dealt_at in rows:
        # A tender that never recorded `offer_sent` gets that step first, so the
        # timeline reads as the ladder the machine allows rather than jumping.
        if status in _PRE_OFFER_SENT:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO request_status_history
                                (request_id, from_status, to_status, changed_by, created_at)
                    VALUES (:request_id,
                            CAST(:from_status AS request_status),
                            CAST('offer_sent' AS request_status),
                            NULL,
                            :created_at)
                    """
                ),
                {"request_id": request_id, "from_status": status, "created_at": quoted_at},
            )

        bind.execute(
            sa.text(
                """
                INSERT INTO request_status_history
                            (request_id, from_status, to_status, changed_by, created_at)
                VALUES (:request_id,
                        CAST('offer_sent' AS request_status),
                        CAST('matched' AS request_status),
                        NULL,
                        :created_at)
                """
            ),
            {"request_id": request_id, "created_at": dealt_at},
        )

    bind.execute(
        sa.text(
            """
            UPDATE requests
               SET status = CAST('matched' AS request_status)
             WHERE id = ANY(:ids)
            """
        ),
        {"ids": [row[0] for row in rows]},
    )
    return len(rows)


def downgrade() -> None:
    """No-op.

    There is no record of which `matched` tenders this touched and which reached
    that status honestly, so a rewind would have to guess — and guessing wrong
    means reopening a tender that has a signed deal against it. The forward
    direction is idempotent (its WHERE clause stops matching once applied), which
    is the property that actually matters here.
    """
