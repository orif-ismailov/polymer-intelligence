"""Chemical compliance (R5 / P5 — T1.1).

  enums  regulation_level, regulation_regime, license_status
         offer_file_kind += 'sds', 'coa'
  tables substances, company_licenses, substance_suggestions
  alter  seller_offers += substance link, CAS/HS, declared concentration,
         cached verdict

`substances` is the source of truth for regulated chemistry: no machine-readable
state registry exists in Uzbekistan (INTEGRATIONS.md §4), so the official ПКМ
lists are digitized into this table by a versioned seed and edited in the admin.

`hs_code` is NOT NULL and `cas` is a nullable unique — the Uzbek lists are keyed
on ТН ВЭД codes and names, while CAS is the international/AI-facing identifier.

`company_licenses` is per REGIME because the four regimes have four different
licensors; "holds a licence" without one would let an ecology certificate unlock
precursor trade.

Every column added to `seller_offers` is nullable: it is a live table fed by two
origins (Telegram sellers and portal companies).

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-28

IMPORTANT: Schema changes only via a NEW migration + DB-doc edit in the same PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REGULATION_LEVEL = postgresql.ENUM(
    "free",
    "docs_required",
    "license_required",
    "prohibited",
    name="regulation_level",
    create_type=False,
)
_REGULATION_REGIME = postgresql.ENUM(
    "precursor_list_iv",
    "explosive_toxic",
    "strong_acting",
    "pkm916_import",
    name="regulation_regime",
    create_type=False,
)
_LICENSE_STATUS = postgresql.ENUM(
    "pending_review",
    "active",
    "expired",
    "revoked",
    "rejected",
    name="license_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. New enum types ─────────────────────────────────────────────────────
    _REGULATION_LEVEL.create(bind, checkfirst=True)
    _REGULATION_REGIME.create(bind, checkfirst=True)
    _LICENSE_STATUS.create(bind, checkfirst=True)

    # `docs_required` names SDS/TDS/COA; the offer-file enum only knew `tds`.
    # ALTER TYPE … ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE offer_file_kind ADD VALUE IF NOT EXISTS 'sds'")
        op.execute("ALTER TYPE offer_file_kind ADD VALUE IF NOT EXISTS 'coa'")

    # ── 2. substances — our own registry, digitized from the ПКМ lists ────────
    op.create_table(
        "substances",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=False),
        sa.Column("name_uz", sa.Text(), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("hs_code", sa.Text(), nullable=False),
        sa.Column("cas", sa.Text(), nullable=True),
        sa.Column("hazard_class", sa.Text(), nullable=True),
        sa.Column(
            "regulation_level", _REGULATION_LEVEL, nullable=False, server_default="free"
        ),
        sa.Column("regulation_regime", _REGULATION_REGIME, nullable=True),
        sa.Column("threshold_concentration_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("exemption_annual_limit", sa.Numeric(12, 3), nullable=True),
        sa.Column("exemption_unit", sa.Text(), nullable=True),
        sa.Column("license_category", sa.Text(), nullable=True),
        sa.Column(
            "required_docs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "synonyms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_act", sa.Text(), nullable=True),
        sa.Column("seed_revision", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_substances_code"),
        sa.UniqueConstraint("cas", name="uq_substances_cas"),
    )
    op.create_index("ix_substances_hs_code", "substances", ["hs_code"])
    op.create_index("ix_substances_level", "substances", ["regulation_level"])

    # ── 3. company_licenses — what a company may trade, per regime ────────────
    op.create_table(
        "company_licenses",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("regime", _REGULATION_REGIME, nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("license_number", sa.Text(), nullable=True),
        sa.Column("issued_by", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status", _LICENSE_STATUS, nullable=False, server_default="pending_review"),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("registered_by", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["verification_documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["registered_by"], ["staff_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_company_licenses_lookup", "company_licenses", ["company_id", "regime", "status"]
    )

    # ── 4. substance_suggestions — the AI-hint journal (FR-C3) ────────────────
    op.create_table(
        "substance_suggestions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("substance_id", sa.BigInteger(), nullable=True),
        sa.Column("suggested_name", sa.Text(), nullable=True),
        sa.Column("suggested_cas", sa.Text(), nullable=True),
        sa.Column("suggested_hs_code", sa.Text(), nullable=True),
        sa.Column("suggested_concentration_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by_user_account_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["seller_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["substance_id"], ["substances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_account_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_substance_suggestions_company", "substance_suggestions", ["company_id", "id"]
    )
    op.create_index("ix_substance_suggestions_offer", "substance_suggestions", ["offer_id"])

    # ── 5. seller_offers — substance link + cached verdict ────────────────────
    op.add_column("seller_offers", sa.Column("substance_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_seller_offers_substance",
        "seller_offers",
        "substances",
        ["substance_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("seller_offers", sa.Column("cas_number", sa.Text(), nullable=True))
    op.add_column("seller_offers", sa.Column("hs_code", sa.Text(), nullable=True))
    op.add_column(
        "seller_offers",
        sa.Column("declared_concentration_pct", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column("seller_offers", sa.Column("compliance_level", _REGULATION_LEVEL, nullable=True))
    op.add_column("seller_offers", sa.Column("compliance_ok", sa.Boolean(), nullable=True))
    op.add_column(
        "seller_offers",
        sa.Column("compliance_missing", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "seller_offers",
        sa.Column("compliance_checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for column in (
        "compliance_checked_at",
        "compliance_missing",
        "compliance_ok",
        "compliance_level",
        "declared_concentration_pct",
        "hs_code",
        "cas_number",
    ):
        op.drop_column("seller_offers", column)
    op.drop_constraint("fk_seller_offers_substance", "seller_offers", type_="foreignkey")
    op.drop_column("seller_offers", "substance_id")

    op.drop_index("ix_substance_suggestions_offer", table_name="substance_suggestions")
    op.drop_index("ix_substance_suggestions_company", table_name="substance_suggestions")
    op.drop_table("substance_suggestions")

    op.drop_index("ix_company_licenses_lookup", table_name="company_licenses")
    op.drop_table("company_licenses")

    op.drop_index("ix_substances_level", table_name="substances")
    op.drop_index("ix_substances_hs_code", table_name="substances")
    op.drop_table("substances")

    bind = op.get_bind()
    _LICENSE_STATUS.drop(bind, checkfirst=True)
    _REGULATION_REGIME.drop(bind, checkfirst=True)
    _REGULATION_LEVEL.drop(bind, checkfirst=True)
    # offer_file_kind keeps 'sds'/'coa': PostgreSQL cannot drop an enum value,
    # and re-creating the type would require rewriting seller_offer_files.
