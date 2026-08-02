"""Company reviews — a counterparty's rating of a company it dealt with.

The «★ 4.8 · 128 отзывов» line on a company profile. One row per (subject,
author company) pair: a review is a standing opinion, not a log, so a second one
replaces nothing and is simply refused — the author edits the one they have.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import CompanyReviewStatus


class CompanyReview(Base):
    """One company's published opinion of another."""

    __tablename__ = "company_reviews"
    __table_args__ = (
        CheckConstraint(
            "company_id <> author_company_id", name="ck_company_review_not_self"
        ),
        CheckConstraint(
            "rating >= 1 AND rating <= 5", name="ck_company_review_rating_range"
        ),
        # A review is a standing opinion per counterparty, not an event log.
        UniqueConstraint(
            "company_id", "author_company_id", name="uq_company_review_pair"
        ),
        Index("ix_company_reviews_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: The company being reviewed.
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    author_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    #: Who typed it, for audit. The public payload shows the COMPANY, never this.
    author_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CompanyReviewStatus] = mapped_column(
        PgEnum(CompanyReviewStatus, name="review_status", create_type=False),
        nullable=False,
        default=CompanyReviewStatus.published,
        server_default="published",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
