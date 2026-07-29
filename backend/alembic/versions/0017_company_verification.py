"""Company verification & portal (R1): accounts, companies, verification, outbox.

Adds the identity-v2 + verification schema (ARCHITECTURE §5, Amendment A1):
  ENUMs   account_status, company_status, company_member_role, company_member_status,
          company_business_role, business_role_status, bank_account_status,
          bank_verification_method, verification_case_type, verification_case_status,
          verification_check_type, verification_check_status, verification_document_kind,
          document_review_status
  tables  user_accounts, sms_send_log, companies, company_members,
          company_business_roles, verification_cases, verification_checks,
          verification_documents, company_bank_accounts, domain_events

Plus dual-origin marketplace bridging: seller_offers gains company_id +
created_by_user_account_id, seller_id becomes NULLABLE with a CHECK that an offer
originates from either a TG seller or a company; sellers/clients gain a dormant
company_id FK.

Tables are created verification_documents-before-company_bank_accounts because the
latter FKs the former (evidence_document_id), closing the only FK cycle.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-23

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (enum name, values) in creation order.
_ENUMS: list[tuple[str, tuple[str, ...]]] = [
    ("account_status", ("active", "blocked")),
    (
        "company_status",
        ("draft", "pending_verification", "verified", "rejected", "suspended", "liquidated"),
    ),
    ("company_member_role", ("owner", "manager", "member")),
    ("company_member_status", ("active", "invited", "removed")),
    (
        "company_business_role",
        (
            "manufacturer",
            "importer",
            "trader",
            "logistics_provider",
            "distributor",
            "laboratory",
            "insurance_provider",
        ),
    ),
    ("business_role_status", ("declared", "confirmed", "revoked")),
    ("bank_account_status", ("unverified", "pending", "verified", "failed", "archived")),
    ("bank_verification_method", ("document", "e_invoice_crosscheck", "bank_api", "manual")),
    ("verification_case_type", ("onboarding", "reverification", "targeted")),
    (
        "verification_case_status",
        (
            "draft",
            "submitted",
            "checks_running",
            "needs_info",
            "pending_review",
            "approved",
            "rejected",
            "cancelled",
        ),
    ),
    (
        "verification_check_type",
        ("tax_id_format", "bank_requisites", "documents_complete", "manual_kyb"),
    ),
    (
        "verification_check_status",
        ("pending", "running", "passed", "warning", "failed", "unavailable", "waived"),
    ),
    (
        "verification_document_kind",
        (
            "registration_certificate",
            "director_id",
            "bank_letter",
            "license",
            "permit",
            "certificate",
            "power_of_attorney",
            "other",
        ),
    ),
    ("document_review_status", ("pending_review", "accepted", "rejected")),
]


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created ENUM type without re-creating it."""
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. ENUM types (must precede tables) ───────────────────────────────────
    for name, values in _ENUMS:
        postgresql.ENUM(*values, name=name).create(bind)

    # ── 2. user_accounts / sms_send_log ───────────────────────────────────────
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("language", sa.String(2), nullable=False, server_default="ru"),
        sa.Column("status", _enum("account_status"), nullable=False, server_default="active"),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
        sa.UniqueConstraint("telegram_user_id"),
    )

    op.create_table(
        "sms_send_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_msg_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_send_log_phone_created", "sms_send_log", ["phone", "created_at"])

    # ── 3. companies ──────────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("jurisdiction", sa.String(2), nullable=False, server_default="UZ"),
        sa.Column("tax_id", sa.Text(), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=True),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("legal_form", sa.Text(), nullable=True),
        sa.Column("legal_address", sa.Text(), nullable=True),
        sa.Column("director_name", sa.Text(), nullable=True),
        sa.Column("registration_date", sa.Date(), nullable=True),
        sa.Column("registry_status", sa.Text(), nullable=True),
        sa.Column("status", _enum("company_status"), nullable=False, server_default="draft"),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reverification_due_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["created_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("jurisdiction", "tax_id", name="uq_company_jurisdiction_tax_id"),
    )

    # ── 4. company_members ────────────────────────────────────────────────────
    op.create_table(
        "company_members",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("member_role", _enum("company_member_role"), nullable=False, server_default="member"),
        sa.Column("status", _enum("company_member_status"), nullable=False, server_default="active"),
        sa.Column("invited_by_user_account_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["invited_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "user_account_id", name="uq_company_member"),
    )

    # ── 5. company_business_roles ─────────────────────────────────────────────
    op.create_table(
        "company_business_roles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("role", _enum("company_business_role"), nullable=False),
        sa.Column("status", _enum("business_role_status"), nullable=False, server_default="declared"),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "role", name="uq_company_business_role"),
    )

    # ── 6. verification_cases ─────────────────────────────────────────────────
    op.create_table(
        "verification_cases",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("case_type", _enum("verification_case_type"), nullable=False, server_default="onboarding"),
        sa.Column("status", _enum("verification_case_status"), nullable=False, server_default="draft"),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_cases_company_id", "verification_cases", ["company_id"])
    # One open case per company (§6.1): the invariant is a DB constraint, not app logic.
    op.create_index(
        "ux_open_case",
        "verification_cases",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('approved','rejected','cancelled')"),
    )

    # ── 7. verification_checks ────────────────────────────────────────────────
    op.create_table(
        "verification_checks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("check_type", _enum("verification_check_type"), nullable=False),
        sa.Column("status", _enum("verification_check_status"), nullable=False, server_default="pending"),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("waived_by", sa.Integer(), nullable=True),
        sa.Column("waive_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["verification_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["waived_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "check_type", name="uq_verification_check"),
    )

    # ── 8. verification_documents (before company_bank_accounts: FK target) ────
    op.create_table(
        "verification_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", _enum("verification_document_kind"), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("uploaded_by_user_account_id", sa.BigInteger(), nullable=False),
        sa.Column("status", _enum("document_review_status"), nullable=False, server_default="pending_review"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["verification_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_user_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_documents_company_id", "verification_documents", ["company_id"])

    # ── 9. company_bank_accounts ──────────────────────────────────────────────
    op.create_table(
        "company_bank_accounts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("bank_mfo", sa.String(5), nullable=False),
        sa.Column("bank_name", sa.Text(), nullable=True),
        sa.Column("account_number_enc", sa.LargeBinary(), nullable=False),
        sa.Column("account_last4", sa.String(4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="UZS"),
        sa.Column("status", _enum("bank_account_status"), nullable=False, server_default="unverified"),
        sa.Column("verification_method", _enum("bank_verification_method"), nullable=True),
        sa.Column("evidence_document_id", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_document_id"], ["verification_documents.id"]),
        sa.ForeignKeyConstraint(["verified_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 10. domain_events (transactional outbox) ──────────────────────────────
    op.create_table(
        "domain_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outbox_unpublished",
        "domain_events",
        ["id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    # ── 11. Marketplace bridging (dual-origin offers, A1) ─────────────────────
    op.add_column("seller_offers", sa.Column("company_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "seller_offers", sa.Column("created_by_user_account_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_seller_offers_company", "seller_offers", "companies", ["company_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_seller_offers_created_by_account",
        "seller_offers",
        "user_accounts",
        ["created_by_user_account_id"],
        ["id"],
    )
    op.alter_column("seller_offers", "seller_id", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_offer_origin",
        "seller_offers",
        "seller_id IS NOT NULL OR company_id IS NOT NULL",
    )

    # Dormant company bridge on the frozen TG identity tables.
    op.add_column("sellers", sa.Column("company_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_sellers_company", "sellers", "companies", ["company_id"], ["id"])
    op.add_column("clients", sa.Column("company_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_clients_company", "clients", "companies", ["company_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()

    # ── Reverse marketplace bridging ──────────────────────────────────────────
    op.drop_constraint("fk_clients_company", "clients", type_="foreignkey")
    op.drop_column("clients", "company_id")
    op.drop_constraint("fk_sellers_company", "sellers", type_="foreignkey")
    op.drop_column("sellers", "company_id")

    op.drop_constraint("ck_offer_origin", "seller_offers", type_="check")
    # Only restore NOT NULL after asserting no company-origin (seller_id NULL) rows exist.
    null_sellers = bind.execute(
        sa.text("SELECT count(*) FROM seller_offers WHERE seller_id IS NULL")
    ).scalar_one()
    if null_sellers:
        raise RuntimeError(
            f"Cannot downgrade: {null_sellers} seller_offers rows have NULL seller_id "
            "(company-origin offers). Reassign or delete them before downgrading 0017."
        )
    op.alter_column("seller_offers", "seller_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("fk_seller_offers_created_by_account", "seller_offers", type_="foreignkey")
    op.drop_constraint("fk_seller_offers_company", "seller_offers", type_="foreignkey")
    op.drop_column("seller_offers", "created_by_user_account_id")
    op.drop_column("seller_offers", "company_id")

    # ── Drop new tables (reverse FK order) ────────────────────────────────────
    op.drop_index("ix_outbox_unpublished", table_name="domain_events")
    op.drop_table("domain_events")
    op.drop_table("company_bank_accounts")
    op.drop_index("ix_verification_documents_company_id", table_name="verification_documents")
    op.drop_table("verification_documents")
    op.drop_table("verification_checks")
    op.drop_index("ux_open_case", table_name="verification_cases")
    op.drop_index("ix_verification_cases_company_id", table_name="verification_cases")
    op.drop_table("verification_cases")
    op.drop_table("company_business_roles")
    op.drop_table("company_members")
    op.drop_table("companies")
    op.drop_index("ix_sms_send_log_phone_created", table_name="sms_send_log")
    op.drop_table("sms_send_log")
    op.drop_table("user_accounts")

    # ── Drop ENUM types (reverse creation order) ──────────────────────────────
    for name, _ in reversed(_ENUMS):
        sa.Enum(name=name).drop(bind, checkfirst=True)
