"""Drop app_settings — the runtime switches moved into the env contract.

The table held operator overrides for a set of feature switches whose defaults
were Python literals in `settings_service._SPECS`. Between the two there was no
single place to read what a deployment was actually running: a fresh database
has no rows, so every rail silently took a default nobody had chosen or could
see. On 31.08.2026 that turned a healthy, fully-credentialed Didox integration
into `503 registry_not_configured` on every company lookup, and finding the
cause meant reading a service module and then querying this table.

The switches now live on `Settings` and are set in `.env` at the repo root.
There is no override path left, so the table is dead weight — and a dead table
that still LOOKS like configuration is worse than none, because the next person
to debug a switch will query it and believe the empty answer.

WHAT IS LOST: any override an operator set through the old dashboard panel. The
values are not migrated into `.env` automatically — they cannot be, since a
migration cannot write to a file the application only reads. Before upgrading a
deployment that used the panel, capture them:

    SELECT key, value FROM app_settings;

and write the corresponding env vars (`settings_service.SPECS` maps each key to
its `env_var`). On a deployment that never used the panel — which is every one
of ours at the time of writing — the table is empty and there is nothing to do.

Revision ID: 0043
Revises: 0042
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("app_settings")


def downgrade() -> None:
    """Recreate the table, empty.

    A downgrade restores the SHAPE, not the overrides — the rows were dropped by
    `upgrade` and a migration has nowhere to keep them. Code at revision 0042
    reads an empty table as "every switch at its code default", which is exactly
    the state a fresh install was always in, so this is a working downgrade
    rather than a silent one: it just means the old defaults apply again.
    """
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True, nullable=False),
        sa.Column("value", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
            sa.Integer(),
            sa.ForeignKey("staff_users.id"),
            nullable=True,
        ),
    )
