"""Manufacturers directory, factory RFQs, and buyer↔manufacturer chat.

Public surface: verified companies with a confirmed `manufacturer` role. Factory
RFQs are the extended buyer form (docs + terms + contact) against one of that
company's published offers. Chat is a 1:1 thread per (buyer, manufacturer) pair.
"""

from __future__ import annotations

import datetime
import decimal
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session, selectinload

from app.core import numbering
from app.core.time import to_display_tz, utcnow
from app.domains.accounts.models import UserAccount
from app.domains.companies import directory as directory_service
from app.domains.companies import service as company_service
from app.domains.companies.models import Company, CompanyBusinessRole
from app.domains.manufacturers.models import (
    FactoryRfq,
    FactoryRfqDocument,
    ManufacturerMessage,
    ManufacturerThread,
)
from app.domains.marketplace.models import SellerOffer
from app.models.enums import (
    BusinessRoleStatus,
    CompanyStatus,
    FactoryRfqDocumentKind,
    FactoryRfqStatus,
    SellerOfferStatus,
)
from app.models.enums import (
    CompanyBusinessRole as CompanyBusinessRoleEnum,
)
from app.services import storage_service

logger = logging.getLogger(__name__)

MAX_CHAT_FILE_BYTES = 10 * 1024 * 1024
MAX_RFQ_DOC_BYTES = 15 * 1024 * 1024


class ManufacturerNotFound(Exception):
    """No verified manufacturer matches the id."""


class NotManufacturerParticipant(Exception):
    """Caller is not a party to this thread / RFQ."""


class OfferNotOnManufacturer(Exception):
    """The offer is not an approved listing of the target manufacturer."""


class SelfManufacturer(Exception):
    """Buyer tried to RFQ / chat with their own company."""


def generate_factory_rfq_number(db: Session) -> str:
    """Next FRQ-YYYY-NNNNNN for the current year in Asia/Tashkent."""
    year = to_display_tz(utcnow(), "Asia/Tashkent").strftime("%Y")
    if not year.isdigit():  # pragma: no cover
        raise RuntimeError(f"Unexpected non-digit year: {year!r}")

    nextval = numbering.next_in_sequence(
        db, f"factory_rfq_seq_{year}", numbering.LOCK_BASE_FACTORY_RFQ + int(year)
    )
    return f"FRQ-{year}-{nextval:06d}"


def _is_confirmed_manufacturer(db: Session, company_id: int) -> bool:
    row = (
        db.query(CompanyBusinessRole.id)
        .filter(
            CompanyBusinessRole.company_id == company_id,
            CompanyBusinessRole.role == CompanyBusinessRoleEnum.manufacturer,
            CompanyBusinessRole.status == BusinessRoleStatus.confirmed,
        )
        .first()
    )
    return row is not None


def get_verified_manufacturer(db: Session, manufacturer_id: int) -> Company:
    company = (
        db.query(Company)
        .options(selectinload(Company.business_roles))
        .filter(Company.id == manufacturer_id)
        .first()
    )
    if (
        company is None
        or company.status != CompanyStatus.verified
        or not _is_confirmed_manufacturer(db, company.id)
    ):
        raise ManufacturerNotFound(str(manufacturer_id))
    return company


def list_manufacturers(
    db: Session,
    *,
    q: str | None = None,
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[Company], int]:
    """Verified companies with a confirmed manufacturer role.

    Delegates to `directory_service`, which serves the same query to the three
    other public directories. Kept as a named function because the cabinet's
    manufacturers page, the factory-RFQ flow and the chat all call it.
    """
    return directory_service.list_by_role(
        db,
        role=CompanyBusinessRoleEnum.manufacturer,
        q=q,
        limit=limit,
        offset=offset,
    )


def offer_count_for(db: Session, company_id: int) -> int:
    return (
        db.query(SellerOffer.id)
        .filter(
            SellerOffer.company_id == company_id,
            SellerOffer.status == SellerOfferStatus.approved,
        )
        .count()
    )


def profile_snippet(company: Company) -> dict[str, object]:
    raw = company.manufacturer_profile or {}
    if not isinstance(raw, dict):
        return {}
    export = raw.get("export_countries")
    export_list = (
        [str(x) for x in export if str(x).strip()] if isinstance(export, list) else []
    )
    employees = raw.get("employees")
    founded = raw.get("founded_year")
    return {
        "production_type": raw.get("production_type") if isinstance(raw.get("production_type"), str) else None,
        "main_products": raw.get("main_products") if isinstance(raw.get("main_products"), str) else None,
        "employees": int(employees) if isinstance(employees, (int, float)) else None,
        "founded_year": int(founded) if isinstance(founded, (int, float)) else None,
        "export_countries": export_list[:16],
        "iso_certification": (
            raw.get("iso_certification")
            if isinstance(raw.get("iso_certification"), str)
            else None
        ),
    }


# ── Factory RFQ ───────────────────────────────────────────────────────────────


def create_factory_rfq(
    db: Session,
    *,
    buyer: Company,
    manufacturer: Company,
    account: UserAccount,
    offer: SellerOffer,
    quantity: decimal.Decimal,
    qty_unit: str,
    target_price: decimal.Decimal | None,
    currency: str,
    incoterms: str | None,
    destination_port: str | None,
    desired_delivery_date: datetime.date | None,
    payment_method: str | None,
    offer_validity: str | None,
    performance_guarantee: str | None,
    inspection_requirement: str | None,
    additional_requirements: str | None,
    contact_name: str,
    contact_position: str | None,
    contact_email: str | None,
    contact_phone: str,
    contact_telegram: str | None,
) -> FactoryRfq:
    if buyer.id == manufacturer.id:
        raise SelfManufacturer()
    if (
        offer.company_id != manufacturer.id
        or offer.status != SellerOfferStatus.approved
    ):
        raise OfferNotOnManufacturer(str(offer.id))

    rfq = FactoryRfq(
        number=generate_factory_rfq_number(db),
        buyer_company_id=buyer.id,
        manufacturer_company_id=manufacturer.id,
        offer_id=offer.id,
        created_by_user_account_id=account.id,
        quantity=quantity,
        qty_unit=qty_unit or "MT",
        target_price=target_price,
        currency=(currency or "USD").upper(),
        incoterms=incoterms,
        destination_port=destination_port,
        desired_delivery_date=desired_delivery_date,
        payment_method=payment_method,
        offer_validity=offer_validity,
        performance_guarantee=performance_guarantee,
        inspection_requirement=inspection_requirement,
        additional_requirements=additional_requirements,
        contact_name=contact_name,
        contact_position=contact_position,
        contact_email=contact_email,
        contact_phone=contact_phone,
        contact_telegram=contact_telegram,
        status=FactoryRfqStatus.submitted,
    )
    db.add(rfq)
    db.flush()
    logger.info(
        "manufacturer_service.create_factory_rfq",
        extra={"rfq_id": rfq.id, "number": rfq.number, "offer_id": offer.id},
    )
    return rfq


def get_factory_rfq_for(
    db: Session, account: UserAccount, rfq_id: int, company_id: int
) -> FactoryRfq:
    company = company_service.get_company_for(db, account, company_id)
    rfq = (
        db.query(FactoryRfq)
        .options(selectinload(FactoryRfq.documents))
        .filter(FactoryRfq.id == rfq_id)
        .first()
    )
    if rfq is None or company.id not in (
        rfq.buyer_company_id,
        rfq.manufacturer_company_id,
    ):
        raise NotManufacturerParticipant(str(rfq_id))
    return rfq


def list_factory_rfqs_for(
    db: Session, company_id: int, *, side: str = "sent"
) -> list[FactoryRfq]:
    query = db.query(FactoryRfq).options(selectinload(FactoryRfq.documents))
    if side == "incoming":
        query = query.filter(FactoryRfq.manufacturer_company_id == company_id)
    else:
        query = query.filter(FactoryRfq.buyer_company_id == company_id)
    return query.order_by(FactoryRfq.id.desc()).all()


def add_factory_rfq_document(
    db: Session,
    rfq: FactoryRfq,
    *,
    kind: FactoryRfqDocumentKind,
    content: bytes,
    filename: str,
) -> FactoryRfqDocument:
    if len(content) > MAX_RFQ_DOC_BYTES:
        raise ValueError("file_too_large")

    existing = (
        db.query(FactoryRfqDocument)
        .filter(
            FactoryRfqDocument.factory_rfq_id == rfq.id,
            FactoryRfqDocument.kind == kind,
        )
        .first()
    )
    key, mime = storage_service.store_factory_rfq_file(rfq.id, content, filename)
    if existing is not None:
        existing.file_name = (filename or "upload").rsplit("/", 1)[-1]
        existing.mime_type = mime
        existing.size_bytes = len(content)
        existing.storage_path = key
        db.flush()
        return existing

    doc = FactoryRfqDocument(
        factory_rfq_id=rfq.id,
        kind=kind,
        file_name=(filename or "upload").rsplit("/", 1)[-1],
        mime_type=mime,
        size_bytes=len(content),
        storage_path=key,
    )
    db.add(doc)
    db.flush()
    return doc


# ── Chat threads ──────────────────────────────────────────────────────────────


def open_or_get_thread(
    db: Session,
    *,
    buyer: Company,
    manufacturer: Company,
    account: UserAccount,
) -> ManufacturerThread:
    if buyer.id == manufacturer.id:
        raise SelfManufacturer()

    existing = (
        db.query(ManufacturerThread)
        .filter(
            ManufacturerThread.buyer_company_id == buyer.id,
            ManufacturerThread.manufacturer_company_id == manufacturer.id,
        )
        .first()
    )
    if existing is not None:
        return existing

    thread = ManufacturerThread(
        buyer_company_id=buyer.id,
        manufacturer_company_id=manufacturer.id,
        created_by_user_account_id=account.id,
    )
    db.add(thread)
    db.flush()
    return thread


def get_thread_for(
    db: Session, account: UserAccount, thread_id: int, company_id: int
) -> ManufacturerThread:
    company = company_service.get_company_for(db, account, company_id)
    thread = db.get(ManufacturerThread, thread_id)
    if thread is None or thread.party_role(company.id) is None:
        raise NotManufacturerParticipant(str(thread_id))
    return thread


def list_threads_for(db: Session, company_id: int) -> list[ManufacturerThread]:
    return (
        db.query(ManufacturerThread)
        .filter(
            sa.or_(
                ManufacturerThread.buyer_company_id == company_id,
                ManufacturerThread.manufacturer_company_id == company_id,
            )
        )
        .order_by(ManufacturerThread.updated_at.desc())
        .all()
    )


def post_message(
    db: Session,
    thread: ManufacturerThread,
    account: UserAccount,
    body: str = "",
    *,
    file_content: bytes | None = None,
    file_name: str | None = None,
    company_id: int,
) -> ManufacturerMessage:
    company = company_service.get_company_for(db, account, company_id)
    if thread.party_role(company.id) is None:
        raise NotManufacturerParticipant(str(thread.id))

    text = (body or "").strip()
    storage_path: str | None = None
    stored_name: str | None = None
    if file_content is not None:
        if len(file_content) > MAX_CHAT_FILE_BYTES:
            raise ValueError("file_too_large")
        storage_path, _mime = storage_service.store_manufacturer_chat_file(
            thread.id, file_content, file_name or "upload"
        )
        stored_name = (file_name or "upload").rsplit("/", 1)[-1]

    if not text and storage_path is None:
        raise ValueError("empty_message")

    message = ManufacturerMessage(
        thread_id=thread.id,
        author_account_id=account.id,
        author_company_id=company.id,
        body=text,
        file_storage_path=storage_path,
        file_name=stored_name,
    )
    db.add(message)
    thread.updated_at = utcnow()
    db.flush()
    return message


def list_messages(
    db: Session,
    thread: ManufacturerThread,
    *,
    after_id: int | None = None,
    limit: int = 100,
) -> list[ManufacturerMessage]:
    query = db.query(ManufacturerMessage).filter(
        ManufacturerMessage.thread_id == thread.id
    )
    if after_id is not None:
        query = query.filter(ManufacturerMessage.id > after_id)
    return query.order_by(ManufacturerMessage.id).limit(max(1, min(limit, 200))).all()
