"""Contracts bounded context (R3 Stage B — TB1.1).

Adds the Deal-Lifecycle seed schema:
  enum   contract_status (draft, pending_counterparty, pending_signatures, active,
         declined, cancelled, expired)
  tables contract_templates, contracts (CHECK initiator <> counterparty),
         contract_signatures (UNIQUE(contract_id, company_id); FK signature_evidence)

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-26

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONTRACT_STATUS = (
    "draft",
    "pending_counterparty",
    "pending_signatures",
    "active",
    "declined",
    "cancelled",
    "expired",
)


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*_CONTRACT_STATUS, name="contract_status").create(bind)

    op.create_table(
        "contract_templates",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=False),
        sa.Column("name_uz", sa.Text(), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("body_storage_path", sa.Text(), nullable=False),
        sa.Column("variables_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_contract_template_code"),
    )

    op.create_table(
        "contracts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("initiator_company_id", sa.BigInteger(), nullable=False),
        sa.Column("counterparty_company_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("generated_document_path", sa.Text(), nullable=True),
        sa.Column("document_sha256", sa.Text(), nullable=True),
        sa.Column("status", _enum("contract_status"), nullable=False, server_default="draft"),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("declined_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["template_id"], ["contract_templates.id"]),
        sa.ForeignKeyConstraint(["initiator_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["counterparty_company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["seller_offers.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.CheckConstraint(
            "initiator_company_id <> counterparty_company_id",
            name="ck_contract_parties_distinct",
        ),
    )
    op.create_index("ix_contracts_initiator", "contracts", ["initiator_company_id"])
    op.create_index("ix_contracts_counterparty", "contracts", ["counterparty_company_id"])

    op.create_table(
        "contract_signatures",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("contract_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("signed_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("signature_evidence_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "signed_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["signed_by_user_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["signature_evidence_id"], ["signature_evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "company_id", name="uq_contract_signature"),
    )


def downgrade() -> None:
    op.drop_table("contract_signatures")
    op.drop_index("ix_contracts_counterparty", table_name="contracts")
    op.drop_index("ix_contracts_initiator", table_name="contracts")
    op.drop_table("contracts")
    op.drop_table("contract_templates")
    postgresql.ENUM(name="contract_status").drop(op.get_bind())
