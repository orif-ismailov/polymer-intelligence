"""
Verification context (R1 — ARCHITECTURE §5): verification_cases,
verification_checks, verification_documents.

A company submits a `VerificationCase`; the case runs a set of `VerificationCheck`
rows (tax-id format, bank requisites, documents complete, manual KYB in R1). A
human (dashboard or Telegram inline) decides the case; approval flips the company
to `verified`. Uploaded evidence lives in `verification_documents` (immutable file
blobs in S3, metadata + sha256 here).

Concurrency (§6.1): human decisions are optimistic (`UPDATE … WHERE status='…'`),
machine evaluators take `SELECT … FOR UPDATE`, and the "one open case per company"
invariant is a partial unique index (`ux_open_case`), not an app-level check.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from app.core.db import Base
from app.models.enums import (
    DocumentReviewStatus,
    VerificationCaseStatus,
    VerificationCaseType,
    VerificationCheckStatus,
    VerificationCheckType,
    VerificationDocumentKind,
)


class VerificationCase(Base):
    """A single verification attempt for a company (onboarding/reverification)."""

    __tablename__ = "verification_cases"
    __table_args__ = (
        # One open case per company (§6.1) — the invariant is a partial unique index.
        Index(
            "ux_open_case",
            "company_id",
            unique=True,
            postgresql_where=text("status NOT IN ('approved','rejected','cancelled')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_type: Mapped[VerificationCaseType] = mapped_column(
        PgEnum(VerificationCaseType, name="verification_case_type", create_type=False),
        nullable=False,
        default=VerificationCaseType.onboarding,
        server_default="onboarding",
    )
    status: Mapped[VerificationCaseStatus] = mapped_column(
        PgEnum(VerificationCaseStatus, name="verification_case_status", create_type=False),
        nullable=False,
        default=VerificationCaseStatus.draft,
        server_default="draft",
    )
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )                                                                             # NULL = auto/telegram actor (see audit_log)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    checks: Mapped[list[VerificationCheck]] = relationship(
        "VerificationCheck", back_populates="case", cascade="all, delete-orphan"
    )


class VerificationCheck(Base):
    """One check within a case; unique per (case_id, check_type)."""

    __tablename__ = "verification_checks"
    __table_args__ = (
        UniqueConstraint("case_id", "check_type", name="uq_verification_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verification_cases.id", ondelete="CASCADE"), nullable=False
    )
    check_type: Mapped[VerificationCheckType] = mapped_column(
        PgEnum(VerificationCheckType, name="verification_check_type", create_type=False),
        nullable=False,
    )
    status: Mapped[VerificationCheckStatus] = mapped_column(
        PgEnum(VerificationCheckStatus, name="verification_check_status", create_type=False),
        nullable=False,
        default=VerificationCheckStatus.pending,
        server_default="pending",
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)   # normalized findings DTO
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    waived_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    waive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped[VerificationCase] = relationship("VerificationCase", back_populates="checks")


class VerificationDocument(Base):
    """Uploaded evidence (registration cert, bank letter, …) — immutable blob in S3."""

    __tablename__ = "verification_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("verification_cases.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[VerificationDocumentKind] = mapped_column(
        PgEnum(VerificationDocumentKind, name="verification_document_kind", create_type=False),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)               # verification/{company_id}/{token}-{name}
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    status: Mapped[DocumentReviewStatus] = mapped_column(
        PgEnum(DocumentReviewStatus, name="document_review_status", create_type=False),
        nullable=False,
        default=DocumentReviewStatus.pending_review,
        server_default="pending_review",
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
