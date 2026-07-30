"""Manufacturers directory: factory RFQs + buyer↔manufacturer chat.

  enums  factory_rfq_status, factory_rfq_document_kind
  tables factory_rfqs, factory_rfq_documents,
         manufacturer_threads, manufacturer_messages

Buyers browse verified companies with a confirmed `manufacturer` role, open a
1:1 chat thread, and submit an extended RFQ (docs + commercial terms + contact)
against one of the factory's published offers — see
`docs/new-design/manufacturer_flow.jpeg`.

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-30

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FACTORY_RFQ_STATUS = (
    "submitted",
    "viewed",
    "in_progress",
    "quoted",
    "closed",
    "rejected",
)
_FACTORY_RFQ_DOC_KIND = (
    "founding_docs",
    "registration_certificate",
    "tax_id",
    "bank_details",
    "import_export_license",
)


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*_FACTORY_RFQ_STATUS, name="factory_rfq_status").create(bind)
    postgresql.ENUM(*_FACTORY_RFQ_DOC_KIND, name="factory_rfq_document_kind").create(bind)

    op.create_table(
        "factory_rfqs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("buyer_company_id", sa.BigInteger(), nullable=False),
        sa.Column("manufacturer_company_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("qty_unit", sa.Text(), nullable=False, server_default="MT"),
        sa.Column("target_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("incoterms", sa.Text(), nullable=True),
        sa.Column("destination_port", sa.Text(), nullable=True),
        sa.Column("desired_delivery_date", sa.Date(), nullable=True),
        sa.Column("payment_method", sa.Text(), nullable=True),
        sa.Column("offer_validity", sa.Text(), nullable=True),
        sa.Column("performance_guarantee", sa.Text(), nullable=True),
        sa.Column("inspection_requirement", sa.Text(), nullable=True),
        sa.Column("additional_requirements", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=False),
        sa.Column("contact_position", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("contact_phone", sa.Text(), nullable=False),
        sa.Column("contact_telegram", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum("factory_rfq_status"),
            nullable=False,
            server_default="submitted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "buyer_company_id <> manufacturer_company_id",
            name="ck_factory_rfq_parties_distinct",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_factory_rfq_quantity_positive"),
        sa.ForeignKeyConstraint(["buyer_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["manufacturer_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["seller_offers.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("number"),
    )
    op.create_index(
        "ix_factory_rfqs_buyer_status",
        "factory_rfqs",
        ["buyer_company_id", "status"],
    )
    op.create_index(
        "ix_factory_rfqs_manufacturer_status",
        "factory_rfqs",
        ["manufacturer_company_id", "status"],
    )

    op.create_table(
        "factory_rfq_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("factory_rfq_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", _enum("factory_rfq_document_kind"), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["factory_rfq_id"], ["factory_rfqs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_rfq_id", "kind", name="uq_factory_rfq_document_kind"
        ),
    )
    op.create_index(
        "ix_factory_rfq_documents_rfq",
        "factory_rfq_documents",
        ["factory_rfq_id", "id"],
    )

    op.create_table(
        "manufacturer_threads",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("buyer_company_id", sa.BigInteger(), nullable=False),
        sa.Column("manufacturer_company_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "buyer_company_id <> manufacturer_company_id",
            name="ck_manufacturer_thread_parties_distinct",
        ),
        sa.ForeignKeyConstraint(["buyer_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["manufacturer_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "buyer_company_id",
            "manufacturer_company_id",
            name="uq_manufacturer_thread_pair",
        ),
    )
    op.create_index(
        "ix_manufacturer_threads_buyer",
        "manufacturer_threads",
        ["buyer_company_id"],
    )
    op.create_index(
        "ix_manufacturer_threads_manufacturer",
        "manufacturer_threads",
        ["manufacturer_company_id"],
    )

    op.create_table(
        "manufacturer_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column("author_account_id", sa.BigInteger(), nullable=False),
        sa.Column("author_company_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("file_storage_path", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "body <> '' OR file_storage_path IS NOT NULL",
            name="ck_manufacturer_message_not_empty",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["manufacturer_threads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["author_company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_manufacturer_messages_thread",
        "manufacturer_messages",
        ["thread_id", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_manufacturer_messages_thread", table_name="manufacturer_messages")
    op.drop_table("manufacturer_messages")
    op.drop_index("ix_manufacturer_threads_manufacturer", table_name="manufacturer_threads")
    op.drop_index("ix_manufacturer_threads_buyer", table_name="manufacturer_threads")
    op.drop_table("manufacturer_threads")
    op.drop_index("ix_factory_rfq_documents_rfq", table_name="factory_rfq_documents")
    op.drop_table("factory_rfq_documents")
    op.drop_index("ix_factory_rfqs_manufacturer_status", table_name="factory_rfqs")
    op.drop_index("ix_factory_rfqs_buyer_status", table_name="factory_rfqs")
    op.drop_table("factory_rfqs")

    bind = op.get_bind()
    postgresql.ENUM(name="factory_rfq_document_kind").drop(bind)
    postgresql.ENUM(name="factory_rfq_status").drop(bind)
