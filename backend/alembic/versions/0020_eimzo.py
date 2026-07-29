"""E-IMZO verification rails (R3 Stage A — TA1.3).

Adds (ARCHITECTURE §9.6, §6.2, §5):
  enum value  verification_check_type += 'eimzo_signature'
  column      companies.identity_locked boolean NOT NULL DEFAULT false
  tables      signature_evidence (immutable evidence of a verified PKCS#7 signature),
              company_person_data (encrypted director/signer PII),
              integration_call_log (outbound provider-call metadata / breaker audit)

`ALTER TYPE ... ADD VALUE` cannot run inside a transaction block, so it runs in an
autocommit block (same pattern as 0004/0014). PostgreSQL cannot DROP an enum value,
so the downgrade leaves 'eimzo_signature' in place (irreversible enum addition).

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-26

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. verification_check_type += 'eimzo_signature' (autocommit) ──────────
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE verification_check_type ADD VALUE IF NOT EXISTS 'eimzo_signature'"
        )

    # ── 2. companies.identity_locked ──────────────────────────────────────────
    op.add_column(
        "companies",
        sa.Column(
            "identity_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ── 3. signature_evidence (immutable, append-only) ────────────────────────
    op.create_table(
        "signature_evidence",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("challenge", sa.Text(), nullable=False),
        sa.Column("pkcs7_storage_path", sa.Text(), nullable=False),
        sa.Column("pkcs7_sha256", sa.Text(), nullable=False),
        sa.Column("cert_subject", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("signed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_signature_evidence_company_id", "signature_evidence", ["company_id"]
    )

    # ── 4. company_person_data (encrypted PII, §6.2) ──────────────────────────
    op.create_table(
        "company_person_data",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("user_account_id", sa.BigInteger(), nullable=True),
        sa.Column("full_name_enc", sa.LargeBinary(), nullable=False),
        sa.Column("pinfl_enc", sa.LargeBinary(), nullable=False),
        sa.Column("pinfl_last4", sa.CHAR(4), nullable=True),
        sa.Column("position", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="eimzo"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_company_person_data_company_id", "company_person_data", ["company_id"]
    )

    # ── 5. integration_call_log (gateway audit, §5/§12) ───────────────────────
    op.create_table(
        "integration_call_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integration_call_log_created", "integration_call_log", ["created_at"]
    )
    op.create_index(
        "ix_integration_call_log_provider",
        "integration_call_log",
        ["provider", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_call_log_provider", table_name="integration_call_log")
    op.drop_index("ix_integration_call_log_created", table_name="integration_call_log")
    op.drop_table("integration_call_log")

    op.drop_index("ix_company_person_data_company_id", table_name="company_person_data")
    op.drop_table("company_person_data")

    op.drop_index("ix_signature_evidence_company_id", table_name="signature_evidence")
    op.drop_table("signature_evidence")

    op.drop_column("companies", "identity_locked")

    # NOTE: PostgreSQL cannot DROP a value from an ENUM type. The 'eimzo_signature'
    # value added in upgrade() is intentionally left in place on downgrade.
