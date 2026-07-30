"""Manufacturers directory: factory RFQs and buyer↔manufacturer chat.

See `docs/new-design/manufacturer_flow.jpeg`. A factory RFQ is the extended form
buyers send to a confirmed manufacturer (docs + commercial terms + contact),
distinct from the lighter trader inquiry on `offer_requests`. Chat lives in a
1:1 thread per (buyer company, manufacturer company) pair — same append-only
shape as deal Trade Room messages, without requiring a deal.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import FactoryRfqDocumentKind, FactoryRfqStatus


class FactoryRfq(Base):
    """A buyer's extended RFQ to a manufacturer against one published offer."""

    __tablename__ = "factory_rfqs"
    __table_args__ = (
        CheckConstraint(
            "buyer_company_id <> manufacturer_company_id",
            name="ck_factory_rfq_parties_distinct",
        ),
        CheckConstraint("quantity > 0", name="ck_factory_rfq_quantity_positive"),
        Index("ix_factory_rfqs_buyer_status", "buyer_company_id", "status"),
        Index(
            "ix_factory_rfqs_manufacturer_status",
            "manufacturer_company_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=func.gen_random_uuid(),
    )
    number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    buyer_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    manufacturer_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    offer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seller_offers.id"), nullable=False
    )
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    qty_unit: Mapped[str] = mapped_column(
        Text, nullable=False, default="MT", server_default="MT"
    )
    target_price: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    incoterms: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_port: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_delivery_date: Mapped[datetime.date | None] = mapped_column(
        Date, nullable=True
    )
    payment_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_validity: Mapped[str | None] = mapped_column(Text, nullable=True)
    performance_guarantee: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspection_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[str] = mapped_column(Text, nullable=False)
    contact_telegram: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[FactoryRfqStatus] = mapped_column(
        PgEnum(FactoryRfqStatus, name="factory_rfq_status", create_type=False),
        nullable=False,
        default=FactoryRfqStatus.submitted,
        server_default="submitted",
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

    documents: Mapped[list[FactoryRfqDocument]] = relationship(
        "FactoryRfqDocument",
        back_populates="factory_rfq",
        cascade="all, delete-orphan",
        order_by="FactoryRfqDocument.id",
    )


class FactoryRfqDocument(Base):
    """One compliance document slot on a factory RFQ. One file per kind."""

    __tablename__ = "factory_rfq_documents"
    __table_args__ = (
        UniqueConstraint(
            "factory_rfq_id", "kind", name="uq_factory_rfq_document_kind"
        ),
        Index("ix_factory_rfq_documents_rfq", "factory_rfq_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    factory_rfq_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("factory_rfqs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[FactoryRfqDocumentKind] = mapped_column(
        PgEnum(
            FactoryRfqDocumentKind,
            name="factory_rfq_document_kind",
            create_type=False,
        ),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    factory_rfq: Mapped[FactoryRfq] = relationship(
        "FactoryRfq", back_populates="documents"
    )


class ManufacturerThread(Base):
    """1:1 chat room between a buyer company and a manufacturer company."""

    __tablename__ = "manufacturer_threads"
    __table_args__ = (
        CheckConstraint(
            "buyer_company_id <> manufacturer_company_id",
            name="ck_manufacturer_thread_parties_distinct",
        ),
        UniqueConstraint(
            "buyer_company_id",
            "manufacturer_company_id",
            name="uq_manufacturer_thread_pair",
        ),
        Index("ix_manufacturer_threads_buyer", "buyer_company_id"),
        Index("ix_manufacturer_threads_manufacturer", "manufacturer_company_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    buyer_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    manufacturer_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    created_by_user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
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

    messages: Mapped[list[ManufacturerMessage]] = relationship(
        "ManufacturerMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ManufacturerMessage.id",
    )

    def party_role(self, company_id: int) -> str | None:
        if company_id == self.buyer_company_id:
            return "buyer"
        if company_id == self.manufacturer_company_id:
            return "manufacturer"
        return None


class ManufacturerMessage(Base):
    """One append-only chat message in a manufacturer thread."""

    __tablename__ = "manufacturer_messages"
    __table_args__ = (
        Index("ix_manufacturer_messages_thread", "thread_id", "id"),
        CheckConstraint(
            "body <> '' OR file_storage_path IS NOT NULL",
            name="ck_manufacturer_message_not_empty",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("manufacturer_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )
    author_company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    file_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    thread: Mapped[ManufacturerThread] = relationship(
        "ManufacturerThread", back_populates="messages"
    )
