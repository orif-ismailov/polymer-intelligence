"""Deals bounded context (R4 / P2 — T1.1).

Adds the Deal Lifecycle core schema:
  enums  deal_status, deal_actor_kind, deal_document_kind, rfq_response_status,
         rfq_visibility
  tables deals (CHECK buyer <> seller; partial-unique contract_id),
         deal_status_history, deal_messages (CHECK body-or-file),
         deal_documents, rfq_responses (partial-unique live response per company)
  alter  requests += required_docs / visibility / visible_company_ids (FR-D10)

`contracts` is deliberately NOT altered: the deal owns the link
(`deals.contract_id`) and the contracts context reaches deals only through
domain events.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-27

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEAL_STATUS = (
    "negotiation",
    "contract_pending",
    "contract_signed",
    "payment_pending",
    "paid_escrow",
    "shipped",
    "delivered",
    "completed",
    "cancelled",
    "disputed",
)
_DEAL_ACTOR_KIND = ("buyer", "seller", "staff", "system")
_DEAL_DOCUMENT_KIND = ("contract", "invoice", "lab_passport", "transport", "other")
_RFQ_RESPONSE_STATUS = ("submitted", "accepted", "not_selected", "withdrawn")
_RFQ_VISIBILITY = ("verified_only", "all", "selected")


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*_DEAL_STATUS, name="deal_status").create(bind)
    postgresql.ENUM(*_DEAL_ACTOR_KIND, name="deal_actor_kind").create(bind)
    postgresql.ENUM(*_DEAL_DOCUMENT_KIND, name="deal_document_kind").create(bind)
    postgresql.ENUM(*_RFQ_RESPONSE_STATUS, name="rfq_response_status").create(bind)
    postgresql.ENUM(*_RFQ_VISIBILITY, name="rfq_visibility").create(bind)

    op.create_table(
        "deals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("buyer_company_id", sa.BigInteger(), nullable=False),
        sa.Column("seller_company_id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.BigInteger(), nullable=True),
        sa.Column("status", _enum("deal_status"), nullable=False, server_default="negotiation"),
        sa.Column("amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="UZS"),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["buyer_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["seller_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["seller_offers.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("number", name="uq_deals_number"),
        sa.CheckConstraint(
            "buyer_company_id <> seller_company_id", name="ck_deal_parties_distinct"
        ),
    )
    op.create_index("ix_deals_buyer_status", "deals", ["buyer_company_id", "status"])
    op.create_index("ix_deals_seller_status", "deals", ["seller_company_id", "status"])
    op.create_index(
        "uq_deals_contract",
        "deals",
        ["contract_id"],
        unique=True,
        postgresql_where=sa.text("contract_id IS NOT NULL"),
    )

    op.create_table(
        "deal_status_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("deal_id", sa.BigInteger(), nullable=False),
        sa.Column("from_status", _enum("deal_status"), nullable=True),
        sa.Column("to_status", _enum("deal_status"), nullable=False),
        sa.Column("actor_kind", _enum("deal_actor_kind"), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deal_status_history_deal", "deal_status_history", ["deal_id", "id"])

    op.create_table(
        "deal_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("deal_id", sa.BigInteger(), nullable=False),
        sa.Column("author_account_id", sa.BigInteger(), nullable=False),
        sa.Column("author_company_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("file_storage_path", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["author_company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "body <> '' OR file_storage_path IS NOT NULL", name="ck_deal_message_not_empty"
        ),
    )
    op.create_index("ix_deal_messages_deal", "deal_messages", ["deal_id", "id"])

    op.create_table(
        "deal_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("deal_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", _enum("deal_document_kind"), nullable=False, server_default="other"),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by_company_id", sa.BigInteger(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deal_documents_deal", "deal_documents", ["deal_id", "id"])

    op.create_table(
        "rfq_responses",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("qty_unit", sa.Text(), nullable=False, server_default="MT"),
        sa.Column("incoterms", _enum("price_basis"), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "status", _enum("rfq_response_status"), nullable=False, server_default="submitted"
        ),
        sa.Column("deal_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rfq_responses_request", "rfq_responses", ["request_id", "id"])
    op.create_index("ix_rfq_responses_company", "rfq_responses", ["company_id", "status"])
    op.create_index(
        "uq_rfq_response_active",
        "rfq_responses",
        ["request_id", "company_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'withdrawn'"),
    )

    # ── RFQ extensions on the existing requests table (FR-D10) ────────────────
    op.add_column("requests", sa.Column("required_docs", postgresql.JSONB(), nullable=True))
    op.add_column(
        "requests",
        sa.Column(
            "visibility", _enum("rfq_visibility"), nullable=False, server_default="verified_only"
        ),
    )
    op.add_column("requests", sa.Column("visible_company_ids", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "visible_company_ids")
    op.drop_column("requests", "visibility")
    op.drop_column("requests", "required_docs")

    op.drop_index("uq_rfq_response_active", table_name="rfq_responses")
    op.drop_index("ix_rfq_responses_company", table_name="rfq_responses")
    op.drop_index("ix_rfq_responses_request", table_name="rfq_responses")
    op.drop_table("rfq_responses")

    op.drop_index("ix_deal_documents_deal", table_name="deal_documents")
    op.drop_table("deal_documents")

    op.drop_index("ix_deal_messages_deal", table_name="deal_messages")
    op.drop_table("deal_messages")

    op.drop_index("ix_deal_status_history_deal", table_name="deal_status_history")
    op.drop_table("deal_status_history")

    op.drop_index("uq_deals_contract", table_name="deals")
    op.drop_index("ix_deals_seller_status", table_name="deals")
    op.drop_index("ix_deals_buyer_status", table_name="deals")
    op.drop_table("deals")

    bind = op.get_bind()
    for name in (
        "rfq_visibility",
        "rfq_response_status",
        "deal_document_kind",
        "deal_actor_kind",
        "deal_status",
    ):
        postgresql.ENUM(name=name).drop(bind)
