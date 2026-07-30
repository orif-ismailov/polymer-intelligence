"""Labs and samples (R5 / P6 — T1.1).

  enums  lab_order_status, sample_request_status
         offer_file_kind += 'lab_passport'
  tables lab_partners, lab_orders, sample_requests
  alter  seller_offers += sample terms + lab_verified

The laboratory analysis itself is a manual process run by a partner lab (TZ §5):
this schema orchestrates the request and stores what came back. Two invariants
are CHECKs rather than service code — a lab order is always about an offer or a
deal, and a `done` order points at the passport it produced. A badge with no
document behind it is the failure the feature exists to prevent.

`sample_requests` copies the seller company onto the row instead of reading it
through the offer: the seller's inbox is queried by that column, and following
the offer would make the inbox depend on the offer never being edited. One LIVE
request per (offer, buyer) is a partial unique index, so a declined request does
not lock the buyer out for good.

Every column added to `seller_offers` has a server default: it is a live table
fed by two origins (Telegram sellers and portal companies).

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-28

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LAB_ORDER_STATUS = postgresql.ENUM(
    "submitted",
    "accepted",
    "sample_awaited",
    "in_analysis",
    "done",
    "rejected",
    name="lab_order_status",
    create_type=False,
)
_SAMPLE_REQUEST_STATUS = postgresql.ENUM(
    "requested",
    "accepted",
    "declined",
    "sent",
    "received",
    "rejected_by_buyer",
    name="sample_request_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. New enum types ─────────────────────────────────────────────────────
    _LAB_ORDER_STATUS.create(bind, checkfirst=True)
    _SAMPLE_REQUEST_STATUS.create(bind, checkfirst=True)

    # The passport is a kind of offer file. ALTER TYPE … ADD VALUE cannot run
    # inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE offer_file_kind ADD VALUE IF NOT EXISTS 'lab_passport'")

    # ── 2. lab_partners — the directory of laboratories we work with ──────────
    op.create_table(
        "lab_partners",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "contacts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 3. lab_orders — a request for an analysis, driven by an operator ──────
    op.create_table(
        "lab_orders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("deal_id", sa.BigInteger(), nullable=True),
        sa.Column("substance_id", sa.BigInteger(), nullable=True),
        sa.Column("sample_volume", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", _LAB_ORDER_STATUS, nullable=False, server_default="submitted"),
        sa.Column("lab_partner_id", sa.BigInteger(), nullable=True),
        sa.Column("result_offer_file_id", sa.Integer(), nullable=True),
        sa.Column("result_deal_document_id", sa.BigInteger(), nullable=True),
        sa.Column("operator_note", sa.Text(), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("handled_by", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "offer_id IS NOT NULL OR deal_id IS NOT NULL", name="ck_lab_order_target"
        ),
        sa.CheckConstraint(
            "status <> 'done' OR result_offer_file_id IS NOT NULL "
            "OR result_deal_document_id IS NOT NULL",
            name="ck_lab_order_done_has_result",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["seller_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["substance_id"], ["substances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lab_partner_id"], ["lab_partners.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["result_offer_file_id"], ["seller_offer_files.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["result_deal_document_id"], ["deal_documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["handled_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number", name="uq_lab_orders_number"),
    )
    op.create_index("ix_lab_orders_status", "lab_orders", ["status", "id"])
    op.create_index("ix_lab_orders_company", "lab_orders", ["company_id", "id"])
    op.create_index("ix_lab_orders_offer", "lab_orders", ["offer_id"])

    # ── 4. sample_requests — a buyer asking for material to hold ──────────────
    op.create_table(
        "sample_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("buyer_company_id", sa.BigInteger(), nullable=False),
        sa.Column("seller_company_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("status", _SAMPLE_REQUEST_STATUS, nullable=False, server_default="requested"),
        sa.Column("qty", sa.Text(), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=False),
        sa.Column("courier", sa.Text(), nullable=True),
        sa.Column("tracking_ref", sa.Text(), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "buyer_company_id <> seller_company_id", name="ck_sample_parties_distinct"
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["seller_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["buyer_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["seller_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_sample_request_active",
        "sample_requests",
        ["offer_id", "buyer_company_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('requested', 'accepted', 'sent')"),
    )
    op.create_index(
        "ix_sample_requests_seller", "sample_requests", ["seller_company_id", "status"]
    )
    op.create_index("ix_sample_requests_buyer", "sample_requests", ["buyer_company_id", "id"])

    # ── 5. seller_offers — sample terms + the independent-analysis flag ───────
    op.add_column(
        "seller_offers",
        sa.Column(
            "samples_available", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("seller_offers", sa.Column("sample_price", sa.Numeric(14, 2), nullable=True))
    op.add_column(
        "seller_offers", sa.Column("sample_dispatch_days", sa.Integer(), nullable=True)
    )
    op.add_column(
        "seller_offers",
        sa.Column("lab_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    for column in (
        "lab_verified",
        "sample_dispatch_days",
        "sample_price",
        "samples_available",
    ):
        op.drop_column("seller_offers", column)

    op.drop_index("ix_sample_requests_buyer", table_name="sample_requests")
    op.drop_index("ix_sample_requests_seller", table_name="sample_requests")
    op.drop_index("uq_sample_request_active", table_name="sample_requests")
    op.drop_table("sample_requests")

    op.drop_index("ix_lab_orders_offer", table_name="lab_orders")
    op.drop_index("ix_lab_orders_company", table_name="lab_orders")
    op.drop_index("ix_lab_orders_status", table_name="lab_orders")
    op.drop_table("lab_orders")

    op.drop_table("lab_partners")

    bind = op.get_bind()
    _SAMPLE_REQUEST_STATUS.drop(bind, checkfirst=True)
    _LAB_ORDER_STATUS.drop(bind, checkfirst=True)
    # offer_file_kind keeps 'lab_passport': PostgreSQL cannot drop an enum value,
    # and re-creating the type would require rewriting seller_offer_files.
