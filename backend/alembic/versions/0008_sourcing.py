"""Internal sourcing layer (Phase 4): inventory_items, partner_suppliers, sourcing_runs.

Three tables backing the AI broker dashboard. No new ENUM types (reuses price_basis).

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-28

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── inventory_items ───────────────────────────────────────────────────────
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("product_id", sa.SmallInteger(), nullable=False),
        sa.Column("grade_text", sa.Text(), nullable=True),
        sa.Column("qty_on_hand", sa.Numeric(14, 3), nullable=False),
        sa.Column("qty_unit", sa.Text(), nullable=False, server_default="MT"),
        sa.Column("cost_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("warehouse_city", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_items_product", "inventory_items", ["product_id"])

    # ── partner_suppliers ─────────────────────────────────────────────────────
    op.create_table(
        "partner_suppliers",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.SmallInteger(), nullable=True),
        sa.Column("grade_text", sa.Text(), nullable=True),
        sa.Column("indicative_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column(
            "incoterms",
            postgresql.ENUM(name="price_basis", create_type=False),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_partner_suppliers_product", "partner_suppliers", ["product_id"])

    # ── sourcing_runs ─────────────────────────────────────────────────────────
    op.create_table(
        "sourcing_runs",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sourcing_runs_request", "sourcing_runs", ["request_id"])


def downgrade() -> None:
    op.drop_table("sourcing_runs")
    op.drop_index("ix_partner_suppliers_product", table_name="partner_suppliers")
    op.drop_table("partner_suppliers")
    op.drop_index("ix_inventory_items_product", table_name="inventory_items")
    op.drop_table("inventory_items")
