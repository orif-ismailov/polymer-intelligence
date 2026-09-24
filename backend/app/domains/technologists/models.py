"""Technologist marketplace tables (migration 0055).

Shaped like `domains/logistics`: a request is broadcast to every published
expert, and each interested expert gets their OWN thread keyed on
`(request, profile)`, so no expert reads a competitor's terms.

The difference that shapes everything else: the answering side is a PERSON
(`technologist_profiles` → `user_accounts`), not a company. So a thread stores
`profile_id` rather than a second company, and a message records which SIDE
wrote it (`author_kind`) rather than an author company.

Status columns are `Text` + CHECK with the value sets in `catalog.py` and below
— not PG ENUMs, so a new value is a code change and not a migration.
"""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

PROFILE_DRAFT = "draft"
PROFILE_PENDING = "pending_review"
PROFILE_PUBLISHED = "published"
PROFILE_REJECTED = "rejected"
PROFILE_SUSPENDED = "suspended"

REQUEST_OPEN = "open"
REQUEST_ASSIGNED = "assigned"
REQUEST_COMPLETED = "completed"
REQUEST_CANCELLED = "cancelled"

OFFER_SUBMITTED = "submitted"
OFFER_ACCEPTED = "accepted"
OFFER_DECLINED = "declined"
OFFER_WITHDRAWN = "withdrawn"

AUTHOR_COMPANY = "company"
AUTHOR_TECHNOLOGIST = "technologist"


def _text_array() -> Mapped[list[str]]:
    return mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'::text[]")
    )


class TechnologistProfile(Base):
    """An expert's professional card — one per account, moderated by staff.

    `published_snapshot` is the card the catalog serves. It is written only on
    approval, so an expert editing a live profile keeps being listed as the
    version staff approved until the edit is approved too — a pending change
    never reaches a factory unreviewed.
    """

    __tablename__ = "technologist_profiles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_review', 'published', 'rejected', 'suspended')",
            name="ck_technologist_profile_status",
        ),
        CheckConstraint(
            "years_experience IS NULL OR years_experience BETWEEN 0 AND 80",
            name="ck_technologist_profile_years",
        ),
        Index("ix_technologist_profiles_status", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    projects_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    countries_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    industries: Mapped[list[str]] = _text_array()
    processes: Mapped[list[str]] = _text_array()
    materials: Mapped[list[str]] = _text_array()
    equipment_brands: Mapped[list[str]] = _text_array()
    work_formats: Mapped[list[str]] = _text_array()
    languages: Mapped[list[str]] = _text_array()
    #: Shown only to a factory that accepted this expert's offer — never public.
    contact_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=PROFILE_DRAFT, server_default=PROFILE_DRAFT
    )
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("staff_users.id"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rating_avg: Mapped[decimal.Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    rating_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TechRequest(Base):
    """A verified company's «нужен технолог», readable by every published expert."""

    __tablename__ = "tech_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'assigned', 'completed', 'cancelled')",
            name="ck_tech_request_status",
        ),
        CheckConstraint("source IN ('form', 'ai')", name="ck_tech_request_source"),
        CheckConstraint(
            "work_format IN ('online', 'on_site', 'both')", name="ck_tech_request_format"
        ),
        CheckConstraint(
            "urgency IN ('urgent', 'week', 'month', 'date')", name="ck_tech_request_urgency"
        ),
        CheckConstraint(
            "capacity IS NULL OR capacity > 0", name="ck_tech_request_capacity_positive"
        ),
        Index("ix_tech_requests_open", "status", "created_at"),
        Index("ix_tech_requests_company", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, server_default=func.gen_random_uuid()
    )
    #: `IMX-TECH-000124` — what both sides quote at each other.
    number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False)
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    need_type: Mapped[str] = mapped_column(Text, nullable=False)
    process: Mapped[str] = mapped_column(Text, nullable=False)
    equipment: Mapped[str] = mapped_column(Text, nullable=False)
    equipment_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    product: Mapped[str] = mapped_column(Text, nullable=False)
    current_material: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_material: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    capacity: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    capacity_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str] = mapped_column(Text, nullable=False)
    needed_by: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    work_format: Mapped[str] = mapped_column(Text, nullable=False)
    languages: Mapped[list[str]] = _text_array()
    budget_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: `form` today; `ai` once the conversational intake writes the same row.
    source: Mapped[str] = mapped_column(Text, nullable=False, default="form", server_default="form")
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=REQUEST_OPEN, server_default=REQUEST_OPEN
    )
    assigned_offer_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tech_offers.id", ondelete="SET NULL", use_alter=True,
                   name="fk_tech_requests_assigned_offer"),
        nullable=True,
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TechRequestInvite(Base):
    """A factory pointed its request at one expert from the catalog."""

    __tablename__ = "tech_request_invites"
    __table_args__ = (
        UniqueConstraint("request_id", "profile_id", name="uq_tech_invite_request_profile"),
        Index("ix_tech_invites_profile", "profile_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tech_requests.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("technologist_profiles.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TechOffer(Base):
    """An expert's priced proposal on a request. One ACTIVE per (request, expert)."""

    __tablename__ = "tech_offers"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_tech_offer_price_positive"),
        CheckConstraint("duration_days > 0", name="ck_tech_offer_duration_positive"),
        CheckConstraint("currency IN ('USD', 'UZS', 'EUR')", name="ck_tech_offer_currency"),
        CheckConstraint(
            "work_format IN ('online', 'on_site', 'both')", name="ck_tech_offer_format"
        ),
        CheckConstraint(
            "status IN ('submitted', 'accepted', 'declined', 'withdrawn')",
            name="ck_tech_offer_status",
        ),
        Index("ix_tech_offers_request", "request_id", "status"),
        Index(
            "uq_tech_offers_active",
            "request_id",
            "profile_id",
            unique=True,
            postgresql_where=text("status IN ('submitted', 'accepted')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tech_requests.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("technologist_profiles.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    work_format: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=OFFER_SUBMITTED, server_default=OFFER_SUBMITTED
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TechThread(Base):
    """One expert's conversation with the factory about one request.

    The company side is not stored — it is `tech_requests.company_id`, one join
    away, and a copy would be a second place for the same fact to be wrong.
    """

    __tablename__ = "tech_threads"
    __table_args__ = (
        UniqueConstraint("request_id", "profile_id", name="uq_tech_thread_request_profile"),
        Index("ix_tech_threads_profile", "profile_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tech_requests.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("technologist_profiles.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TechMessage(Base):
    """One append-only line in a tech thread."""

    __tablename__ = "tech_messages"
    __table_args__ = (
        CheckConstraint(
            "author_kind IN ('company', 'technologist')", name="ck_tech_message_author_kind"
        ),
        CheckConstraint(
            "body <> '' OR file_storage_path IS NOT NULL", name="ck_tech_message_not_empty"
        ),
        Index("ix_tech_messages_thread", "thread_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tech_threads.id", ondelete="CASCADE"), nullable=False
    )
    #: Which SIDE wrote it — stored, because "mine" is a side, not an account:
    #: two members of one factory see each other's lines as their own.
    author_kind: Mapped[str] = mapped_column(Text, nullable=False)
    author_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    file_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TechReview(Base):
    """The factory's 1–5 verdict on a completed request. Immutable, one per request."""

    __tablename__ = "tech_reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_tech_review_rating"),
        Index("ix_tech_reviews_profile", "profile_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tech_requests.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("technologist_profiles.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
