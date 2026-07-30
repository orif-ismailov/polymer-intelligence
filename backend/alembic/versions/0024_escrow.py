"""Payments bounded context (R4 / P3 — T1.1).

Adds the escrow rails:
  enum   escrow_status (pending, funded, released, refunded)
  tables escrow_payments (one per deal; mode frozen at creation; a staff id +
         timestamp per marked movement — the stub-mode evidence trail),
         provider_events (webhook inbox, unique per provider+external_id so a
         retried bank callback cannot be applied twice)

No bank account details are stored anywhere: the invoice is issued by the
partner bank, and holding account numbers would buy nothing operationally while
making this table a fraud target.

`provider_events` lands here rather than in P7 because the idempotency
guarantee belongs to the schema, not to whichever adapter arrives later — P7
adds the client and the webhook route against a table that already exists.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-27

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ESCROW_STATUS = ("pending", "funded", "released", "refunded")


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*_ESCROW_STATUS, name="escrow_status").create(bind)

    op.create_table(
        "escrow_payments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("deal_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="UZS"),
        sa.Column(
            "status",
            postgresql.ENUM(name="escrow_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("mode", sa.Text(), nullable=False, server_default="stub"),
        sa.Column("provider_ref", sa.Text(), nullable=True),
        sa.Column("funded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("released_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("funded_marked_by", sa.BigInteger(), nullable=True),
        sa.Column("released_marked_by", sa.BigInteger(), nullable=True),
        sa.Column("refunded_marked_by", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id", name="uq_escrow_payments_deal"),
    )
    op.create_index("ix_escrow_payments_status", "escrow_payments", ["status", "id"])

    op.create_table(
        "provider_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_provider_events_external"),
    )
    op.create_index("ix_provider_events_unprocessed", "provider_events", ["processed", "id"])


def downgrade() -> None:
    op.drop_index("ix_provider_events_unprocessed", table_name="provider_events")
    op.drop_table("provider_events")

    op.drop_index("ix_escrow_payments_status", table_name="escrow_payments")
    op.drop_table("escrow_payments")

    postgresql.ENUM(name="escrow_status").drop(op.get_bind())
