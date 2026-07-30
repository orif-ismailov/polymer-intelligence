"""State-registry evidence (R6 / P7.c — T4.1).

  enums  verification_check_type += 'gov_registry', 'vat_status'
  tables registry_snapshots

One table, one idea: what a registry told us about a company is EVIDENCE, and
evidence is immutable. No `updated_at`, and no update path anywhere in the
codebase — a fresh check is a new row, and the history of a company's registry
checks is the sequence of its rows.

That is load-bearing because two different things write these rows. `source =
'registry'` means an API answered (ПЦД, once that access exists) and `created_by`
is NULL — nobody asserted anything. `source = 'manual'` means an operator read an
open service (my.soliq.uz for VAT, license.gov.uz for licences), transcribed the
result and attached a screenshot; `created_by` is the staff member whose name is
on the claim. Overwriting a row would erase which of the two said what, and when.

`kind`/`source` are Text + CHECK rather than PG enums, matching
`escrow_payments.mode`: small closed sets whose members are also plain constants
in service code.

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-28

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Two new verification checks ────────────────────────────────────────
    # APPEND-only: the values are a PG enum and `ALTER TYPE` cannot reorder or
    # rename. Neither can run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE verification_check_type ADD VALUE IF NOT EXISTS 'gov_registry'"
        )
        op.execute("ALTER TYPE verification_check_type ADD VALUE IF NOT EXISTS 'vat_status'")

    # ── 2. registry_snapshots — immutable observations ────────────────────────
    op.create_table(
        "registry_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("raw_status", sa.Text(), nullable=True),
        sa.Column("evidence_path", sa.Text(), nullable=True),
        sa.Column("evidence_sha256", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "kind IN ('company', 'licenses', 'vat')", name="ck_registry_snapshot_kind"
        ),
        sa.CheckConstraint(
            "source IN ('registry', 'manual')", name="ck_registry_snapshot_source"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # "The latest snapshot of kind X for company Y" is the only read path.
    op.create_index(
        "ix_registry_snapshots_lookup",
        "registry_snapshots",
        ["company_id", "kind", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_registry_snapshots_lookup", table_name="registry_snapshots")
    op.drop_table("registry_snapshots")
    # verification_check_type keeps 'gov_registry'/'vat_status': PostgreSQL cannot
    # drop an enum value, and re-creating the type would mean rewriting
    # verification_checks. Same reasoning as 0028 and offer_file_kind.
