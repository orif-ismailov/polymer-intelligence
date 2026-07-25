"""
Company Registry (R1 — ARCHITECTURE §5 with Amendment A1): companies,
company_members, company_business_roles, company_bank_accounts.

A `Company` is created by a `UserAccount` (the creator becomes the owner member)
and verified independently through a `VerificationCase`. Membership is keyed by
`user_account_id` (A1) — `telegram_user_id` identities are a separate frozen world.

`public_id` (UUID) is the stable external reference (deal module, gov reporting)
so we never leak sequence counts. Bank account numbers are app-layer encrypted
(`account_number_enc`, see app/core/crypto.py); only the last 4 digits are stored
in clear for display/masking.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import (
    BankAccountStatus,
    BankVerificationMethod,
    BusinessRoleStatus,
    CompanyMemberRole,
    CompanyMemberStatus,
    CompanyStatus,
)
from app.models.enums import (
    CompanyBusinessRole as CompanyBusinessRoleEnum,
)


class Company(Base):
    """A legal entity registered on the platform, verified independently."""

    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("jurisdiction", "tax_id", name="uq_company_jurisdiction_tax_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=func.gen_random_uuid(),
    )
    jurisdiction: Mapped[str] = mapped_column(
        String(2), nullable=False, default="UZ", server_default="UZ"
    )
    tax_id: Mapped[str] = mapped_column(Text, nullable=False)                      # STIR/INN
    legal_name: Mapped[str | None] = mapped_column(Text, nullable=True)            # from registry once verified
    short_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_form: Mapped[str | None] = mapped_column(Text, nullable=True)            # OOO/AJ/ChP…
    legal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    director_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    registry_status: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )                                                                             # gov-reported status (populated in P2)
    status: Mapped[CompanyStatus] = mapped_column(
        PgEnum(CompanyStatus, name="company_status", create_type=False),
        nullable=False,
        default=CompanyStatus.draft,
        server_default="draft",
    )
    verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reverification_due_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    identity_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )                                                                             # R3: E-IMZO-confirmed requisites are frozen (reject PATCH)
    counterparty_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("counterparties.id"), nullable=True
    )                                                                             # bridge into the intelligence loop
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list[CompanyMember]] = relationship(
        "CompanyMember", back_populates="company", cascade="all, delete-orphan"
    )
    business_roles: Mapped[list[CompanyBusinessRole]] = relationship(
        "CompanyBusinessRole", back_populates="company", cascade="all, delete-orphan"
    )
    bank_accounts: Mapped[list[CompanyBankAccount]] = relationship(
        "CompanyBankAccount", back_populates="company", cascade="all, delete-orphan"
    )


class CompanyMember(Base):
    """Membership of a UserAccount in a Company (A1: keyed by user_account_id)."""

    __tablename__ = "company_members"
    __table_args__ = (
        UniqueConstraint("company_id", "user_account_id", name="uq_company_member"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    member_role: Mapped[CompanyMemberRole] = mapped_column(
        PgEnum(CompanyMemberRole, name="company_member_role", create_type=False),
        nullable=False,
        default=CompanyMemberRole.member,
        server_default="member",
    )
    status: Mapped[CompanyMemberStatus] = mapped_column(
        PgEnum(CompanyMemberStatus, name="company_member_status", create_type=False),
        nullable=False,
        default=CompanyMemberStatus.active,
        server_default="active",
    )
    invited_by_user_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped[Company] = relationship("Company", back_populates="members")


class CompanyBusinessRole(Base):
    """A declared business role (manufacturer/importer/…) of a company."""

    __tablename__ = "company_business_roles"
    __table_args__ = (
        UniqueConstraint("company_id", "role", name="uq_company_business_role"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[CompanyBusinessRoleEnum] = mapped_column(
        PgEnum(CompanyBusinessRoleEnum, name="company_business_role", create_type=False),
        nullable=False,
    )
    status: Mapped[BusinessRoleStatus] = mapped_column(
        PgEnum(BusinessRoleStatus, name="business_role_status", create_type=False),
        nullable=False,
        default=BusinessRoleStatus.declared,
        server_default="declared",
    )
    confirmed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped[Company] = relationship("Company", back_populates="business_roles")


class CompanyBankAccount(Base):
    """A company bank account — number encrypted at the app layer (§15)."""

    __tablename__ = "company_bank_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    bank_mfo: Mapped[str] = mapped_column(String(5), nullable=False)              # 5-digit MFO
    bank_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_number_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # Fernet ciphertext
    account_last4: Mapped[str] = mapped_column(String(4), nullable=False)          # clear, for masking
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="UZS", server_default="UZS"
    )
    status: Mapped[BankAccountStatus] = mapped_column(
        PgEnum(BankAccountStatus, name="bank_account_status", create_type=False),
        nullable=False,
        default=BankAccountStatus.unverified,
        server_default="unverified",
    )
    verification_method: Mapped[BankVerificationMethod | None] = mapped_column(
        PgEnum(BankVerificationMethod, name="bank_verification_method", create_type=False),
        nullable=True,
    )
    evidence_document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("verification_documents.id"), nullable=True
    )
    verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped[Company] = relationship("Company", back_populates="bank_accounts")
