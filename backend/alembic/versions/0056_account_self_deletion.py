"""Account self-deletion: `account_status` gains `deleted`.

The mobile stores (Google Play, App Store) require an in-app way to delete an
account, and the portal gets the same button. Deletion keeps the `user_accounts`
ROW — ~40 foreign keys point at it from contracts, deals, signatures, verification
cases and offers, and those are company records under legal retention — and turns
it into a tombstone: personal fields scrubbed, credentials dropped, status
`deleted` (`app/domains/accounts/deletion.py`).

Why a new value rather than `blocked`: `blocked` is a staff decision that staff can
reverse (`/admin/portal-accounts/{id}/unblock`), and the dashboard offers exactly
that button on it. A deletion is the person's decision and is final; the admin
service refuses every credential and status action on a `deleted` row. Keeping the
two apart is also what lets the staff list say which one happened.

`get_current_account`, `refresh` and `authenticate` all refuse anything that is not
`active`, so the new value fails closed everywhere without being named there.

Revision ID: 0056
Revises: 0055
Create Date: 2026-09-25

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE … ADD VALUE cannot run inside a transaction block; Alembic wraps
    # each migration in one, so it is suspended here (same as 0028, 0041, 0048).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE account_status ADD VALUE IF NOT EXISTS 'deleted'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE … DROP VALUE (the wall 0042 and 0048 hit too). The
    # value stays; a deleted row is still a valid tombstone under the old code,
    # which refuses every non-`active` status.
    pass
