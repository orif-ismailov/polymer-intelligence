"""Move contracts out of `pending_counterparty` — the «accept the terms» step is gone.

The counterparty could never edit the terms, so accepting them and then signing
them were two clicks for one decision. Sending a draft now goes straight to
`pending_signatures`, where the counterparty signs or declines.

A contract already waiting in `pending_counterparty` would otherwise be stranded:
no route leads out of it any more. It is moved to where accepting would have
taken it. `updated_at` is left alone so the 30-day expiry clock keeps counting
from the last thing a person did, not from this migration.

The enum value itself stays — Postgres cannot drop one without rebuilding the
type and every column that uses it, which buys nothing here.

Downgrade is a no-op: nothing records which rows were moved, and moving every
`pending_signatures` row back would invent an acceptance step for contracts
that never had one.

Revision ID: 0052
Revises: 0051
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE contracts SET status = 'pending_signatures' "
            "WHERE status = 'pending_counterparty'"
        )
    )


def downgrade() -> None:
    pass
