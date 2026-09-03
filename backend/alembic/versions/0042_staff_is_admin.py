"""Staff authorization: replace the four-role enum with a single `is_admin` flag.

`staff_role` (admin/analyst/trader/viewer) was a taxonomy nobody could use: no
endpoint ever created a staff user or changed a role — `StaffUser(...)` was
constructed only by `app/seed/seed_staff.py`, and `/admin/users` had a single
GET. So the four values were fixed at seed time and could only be changed with
SQL. Two of them barely meant anything either: `trader` gated 5 endpoints and
granted nothing an analyst lacked, and `viewer` gated nothing at all (it was
read-only only because no viewer-reachable endpoint happened to mutate).

This collapses authorization to one question — are you an administrator — as the
foundation for per-user, per-page access (migration 0043), where `is_admin`
becomes the superuser flag that bypasses the page matrix.

The backfill is `role = 'admin'`, so an existing analyst/trader/viewer keeps
their login and loses their reach. That is the intended direction: after 0043 an
admin grants them pages explicitly, and until then nobody holds access they were
never deliberately given.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-31

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff_users",
        sa.Column(
            "is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.execute(sa.text("UPDATE staff_users SET is_admin = (role = 'admin')"))

    op.drop_column("staff_users", "role")
    # No ALTER TYPE … DROP VALUE is needed: the only column on this type is gone,
    # so the type itself drops outright rather than being rebuilt.
    op.execute(sa.text("DROP TYPE staff_role"))


def downgrade() -> None:
    staff_role = sa.Enum(
        "admin", "analyst", "trader", "viewer", name="staff_role"
    )
    staff_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "staff_users",
        sa.Column(
            "role",
            staff_role,
            nullable=False,
            server_default="viewer",
        ),
    )
    # Lossy by nature: analyst/trader/viewer were flattened to `false` on the way
    # up and cannot be told apart on the way down. Everyone who was an admin
    # becomes one again; everyone else lands on the least-privileged value.
    op.execute(sa.text("UPDATE staff_users SET role = 'admin' WHERE is_admin"))
    op.drop_column("staff_users", "is_admin")
