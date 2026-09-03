"""Per-user, per-page staff access.

Migration 0042 collapsed the unusable four-role enum to a single `is_admin`
flag, which left the dashboard administrator-only. This is the other half: a
non-administrator is granted access one page at a time, at `read` or `write`.

ONLY GRANTS ARE STORED. There is deliberately no `none` level and no row meaning
"denied" — a page a user holds no row for is a page they cannot reach. The
alternative (a row per user per page, with an explicit `none`) would need
backfilling every time a page is added, and forgetting that backfill would open
the new page to everyone rather than close it.

`page` is a text key from `app.core.pages.PAGES` with no foreign key to a lookup
table, because the catalog ships with the code that reads it. A table would let
the two disagree about which pages exist, and the loser of that disagreement is
a permission nothing enforces.

No data migration: `is_admin` was already backfilled in 0042, and every other
account is left with no grants. That is the safe direction — the three legacy
seed accounts (analyst/trader/viewer) reach nothing until an administrator opens
a page for them, rather than silently keeping a reach nobody chose.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-31

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_page_access",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("page", sa.Text(), nullable=False),
        sa.Column("access", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"], ["staff_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("staff_user_id", "page", name="uq_staff_page_access"),
        # A CHECK rather than a PG ENUM: two stable values, and Postgres has no
        # ALTER TYPE … DROP VALUE — which is exactly what made `staff_role`
        # expensive to retire one migration ago.
        sa.CheckConstraint(
            "access IN ('read', 'write')", name="ck_staff_page_access_level"
        ),
    )
    # Every guarded request resolves (user → their grants); the unique constraint
    # already indexes that prefix, so no second index is added here.


def downgrade() -> None:
    op.drop_table("staff_page_access")
