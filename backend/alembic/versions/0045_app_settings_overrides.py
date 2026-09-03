"""Recreate app_settings — this time as an OVERRIDE store, not a second truth.

Migration `0043` dropped a table of the same name two revisions ago, and the
reason it went is worth restating, because this one is not a revert.

The old table held a value for a switch whose DEFAULT was a Python literal in
`settings_service._SPECS`. Between those two places there was nowhere to read
what a deployment was actually running: a fresh database has no rows, so every
rail resolved to a number nobody had chosen and nothing displayed. On
31.08.2026 that turned a healthy, fully-credentialed Didox integration into
`503 registry_not_configured` on every company lookup.

The defaults have since moved onto `Settings`, where `.env` sets them and
`deploy/.env.example` documents every one. That has not changed and does not
change here. What this table adds is a layer ON TOP of that contract:

    effective value = the override row, if one exists, else the env value

Both halves are shown side by side in the admin panel with the env var named
and a reset action, so the failure this table caused the first time round is
not reachable: a missing row no longer means "some default in code", it means
the value printed in `.env.example`, and an override is visible as an override.

Columns:
  key         a `settings_service.SPECS` key, validated in the service rather
              than by a foreign key — the catalog ships with the code that
              reads it, and a lookup table would let the two disagree.
  value       JSONB, so a bool stays a bool and `null` is a legal override for
              the nullable settings (the notify chat ids).
  is_secret   this row's `value` is Fernet ciphertext (`app.core.crypto`), not
              plaintext. A column rather than a lookup into SPECS, because the
              loader has to know how to read a row before it can consult
              anything, and a spec that stops being `sensitive` must not turn
              existing ciphertext into a value we hand to a provider.
  updated_by  who changed it. Nullable for the same reason as `audit_log`:
              a row written by a migration or a script has no staff member.

Revision ID: 0045
Revises: 0044
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "is_secret",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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


def downgrade() -> None:
    """Drop the overrides.

    Every switch then resolves to its `.env` value, which is the documented
    contract and the state a deployment that never opened the panel is already
    in — so this is a working downgrade rather than a silent one. It does mean
    an operator's overrides are gone; capture them first if that matters:

        SELECT key, value FROM app_settings WHERE NOT is_secret;

    (The secret rows are ciphertext and only mean anything to a deployment
    holding the same `VERIFICATION_ENC_KEY`; re-enter those by hand.)
    """
    op.drop_table("app_settings")
