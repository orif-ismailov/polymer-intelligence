"""Seller marketplace (Phase 2): sellers, seller_offers, seller_offer_files.

Adds two ENUM types (seller_offer_status, offer_file_kind) and three tables for
the seller side of the platform. Sellers self-register; offers are moderated
before becoming public (status=approved). Reuses the existing price_basis ENUM.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-28

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. ENUM types (must precede tables) ───────────────────────────────────
    seller_offer_status = postgresql.ENUM(
        "draft", "pending_moderation", "approved", "rejected", "archived",
        name="seller_offer_status",
    )
    seller_offer_status.create(op.get_bind())

    offer_file_kind = postgresql.ENUM(
        "image", "tds", "certificate", "other",
        name="offer_file_kind",
    )
    offer_file_kind.create(op.get_bind())

    # ── 2. sellers ────────────────────────────────────────────────────────────
    op.create_table(
        "sellers",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("telegram_username", sa.Text(), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )

    # ── 3. seller_offers ──────────────────────────────────────────────────────
    op.create_table(
        "seller_offers",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("seller_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.SmallInteger(), nullable=True),
        sa.Column("product_text", sa.Text(), nullable=True),
        sa.Column("grade_text", sa.Text(), nullable=True),
        sa.Column("polymer_type", sa.Text(), nullable=True),
        sa.Column("qty_available", sa.Numeric(14, 3), nullable=False),
        sa.Column("qty_unit", sa.Text(), nullable=False, server_default="MT"),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column(
            "incoterms",
            postgresql.ENUM(name="price_basis", create_type=False),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("warehouse_city", sa.Text(), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("min_order_qty", sa.Numeric(14, 3), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="seller_offer_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("moderated_by", sa.Integer(), nullable=True),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("signal_id", sa.BigInteger(), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["moderated_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seller_offers_status_created", "seller_offers", ["status", "created_at"])
    op.create_index("ix_seller_offers_product", "seller_offers", ["product_id"])
    op.create_index("ix_seller_offers_seller", "seller_offers", ["seller_id"])

    # ── 4. seller_offer_files ─────────────────────────────────────────────────
    op.create_table(
        "seller_offer_files",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(name="offer_file_kind", create_type=False),
            nullable=False,
            server_default="image",
        ),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["seller_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("seller_offer_files")
    op.drop_index("ix_seller_offers_seller", table_name="seller_offers")
    op.drop_index("ix_seller_offers_product", table_name="seller_offers")
    op.drop_index("ix_seller_offers_status_created", table_name="seller_offers")
    op.drop_table("seller_offers")
    op.drop_table("sellers")

    bind = op.get_bind()
    sa.Enum(name="offer_file_kind").drop(bind, checkfirst=True)
    sa.Enum(name="seller_offer_status").drop(bind, checkfirst=True)
