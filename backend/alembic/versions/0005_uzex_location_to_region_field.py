"""Remap the UZEX warehouse-location column from counterparty_text to region.

The uzex_offers and uzex_contracts source configs mapped the "Omborning joylashuvi"
(warehouse / delivery location) column to `counterparty_text`. That field feeds raw
counterparty linking, so locations like "Таш обл" / "Джизакская обл." were being treated
as counterparties, while signals.region stayed NULL. signal_service now reads
payload['region'] into Signal.region, and the seed config maps that column to `region`.

This migration rewrites the already-seeded production rows so they match: the location
column index becomes "region" instead of "counterparty_text". Guarded so it is
idempotent and a no-op on a freshly-seeded DB (where the config is already correct) or
before the sources are seeded at all.

  - uzex_offers:    config.columns[7]  counterparty_text -> region
  - uzex_contracts: config.columns[5]  counterparty_text -> region

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-24

IMPORTANT: Schema/data changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (adapter, column index, old field name, new field name)
_REMAPS: list[tuple[str, int, str, str]] = [
    ("uzex_offers", 7, "counterparty_text", "region"),
    ("uzex_contracts", 5, "counterparty_text", "region"),
]


def _apply(remaps: list[tuple[str, int, str, str]]) -> None:
    conn = op.get_bind()
    for adapter, idx, frm, to in remaps:
        # idx is a trusted int from _REMAPS (not user input); inline it so the jsonb
        # array index resolves to integer access — a bound :idx param is type-ambiguous
        # for the `->>` operator and silently matches nothing.
        conn.execute(
            sa.text(
                f"""
                UPDATE sources
                   SET config = jsonb_set(config, '{{columns,{idx}}}', to_jsonb(CAST(:to AS text)))
                 WHERE adapter = :adapter
                   AND config -> 'columns' ->> {idx} = :frm
                """  # noqa: S608 — idx is an int constant from _REMAPS, not user input
            ),
            {"to": to, "adapter": adapter, "frm": frm},
        )


def upgrade() -> None:
    _apply(_REMAPS)


def downgrade() -> None:
    # Reverse the remap (region -> counterparty_text at the same indices).
    _apply([(adapter, idx, to, frm) for adapter, idx, frm, to in _REMAPS])
