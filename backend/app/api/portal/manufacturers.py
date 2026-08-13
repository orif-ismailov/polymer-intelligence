"""Portal manufacturers directory, factory RFQs, and chat. Under /api/v1/portal.

Buyers browse verified companies with a confirmed `manufacturer` role, open a
1:1 chat thread, and submit an extended RFQ against one of the factory's
published offers (`docs/new-design/manufacturer_flow.jpeg`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.companies import _company_or_404, _require_business_role
from app.core.db import get_db
from app.domains.marketplace import service as offer_service
from app.domains.marketplace.models import SellerOffer
from app.models.accounts import UserAccount
from app.models.companies import Company
from app.models.enums import FactoryRfqDocumentKind
from app.models.manufacturers import FactoryRfq, ManufacturerMessage, ManufacturerThread
from app.schemas.portal_manufacturers import (
    FactoryRfqCreateIn,
    FactoryRfqDocumentOut,
    FactoryRfqOut,
    ManufacturerCardOut,
    ManufacturerListOut,
    ManufacturerMessageOut,
    ManufacturerMessagePageOut,
    ManufacturerThreadOpenIn,
    ManufacturerThreadOut,
)
from app.services import company_service, manufacturer_service, storage_service

router = APIRouter(prefix="/portal/manufacturers", tags=["portal-manufacturers"])


def _card(db: Session, company: Company) -> ManufacturerCardOut:
    snippet = manufacturer_service.profile_snippet(company)
    export_raw = snippet.get("export_countries")
    export_countries = (
        [str(x) for x in export_raw] if isinstance(export_raw, list) else []
    )
    employees = snippet.get("employees")
    founded = snippet.get("founded_year")
    production_type = snippet.get("production_type")
    main_products = snippet.get("main_products")
    iso = snippet.get("iso_certification")
    return ManufacturerCardOut(
        id=company.id,
        public_id=company.public_id,
        legal_name=company.legal_name,
        short_name=company.short_name,
        legal_address=company.legal_address,
        jurisdiction=company.jurisdiction,
        logo_url=storage_service.presign_company_logo(company),
        verified_at=company.verified_at,
        offer_count=manufacturer_service.offer_count_for(db, company.id),
        production_type=production_type if isinstance(production_type, str) else None,
        main_products=main_products if isinstance(main_products, str) else None,
        employees=employees if isinstance(employees, int) else None,
        founded_year=founded if isinstance(founded, int) else None,
        export_countries=export_countries,
        iso_certification=iso if isinstance(iso, str) else None,
    )


def _doc_out(doc: object) -> FactoryRfqDocumentOut:
    from app.models.manufacturers import FactoryRfqDocument

    assert isinstance(doc, FactoryRfqDocument)
    return FactoryRfqDocumentOut(
        id=doc.id,
        kind=str(doc.kind),
        file_name=doc.file_name,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        created_at=doc.created_at,
    )


def _rfq_out(db: Session, rfq: FactoryRfq) -> FactoryRfqOut:
    offer = db.get(SellerOffer, rfq.offer_id)
    manufacturer = db.get(Company, rfq.manufacturer_company_id)
    title = None
    if offer is not None:
        title = offer.product_text or offer.grade_text
    name = None
    if manufacturer is not None:
        name = manufacturer.short_name or manufacturer.legal_name
    return FactoryRfqOut(
        id=rfq.id,
        public_id=rfq.public_id,
        number=rfq.number,
        buyer_company_id=rfq.buyer_company_id,
        manufacturer_company_id=rfq.manufacturer_company_id,
        offer_id=rfq.offer_id,
        offer_title=title,
        manufacturer_name=name,
        quantity=rfq.quantity,
        qty_unit=rfq.qty_unit,
        target_price=rfq.target_price,
        currency=rfq.currency,
        incoterms=rfq.incoterms,
        destination_port=rfq.destination_port,
        desired_delivery_date=rfq.desired_delivery_date,
        payment_method=rfq.payment_method,
        offer_validity=rfq.offer_validity,
        performance_guarantee=rfq.performance_guarantee,
        inspection_requirement=rfq.inspection_requirement,
        additional_requirements=rfq.additional_requirements,
        contact_name=rfq.contact_name,
        contact_position=rfq.contact_position,
        contact_email=rfq.contact_email,
        contact_phone=rfq.contact_phone,
        contact_telegram=rfq.contact_telegram,
        status=str(rfq.status),
        documents=[_doc_out(d) for d in rfq.documents],
        created_at=rfq.created_at,
    )


def _thread_out(
    db: Session, thread: ManufacturerThread, *, company_id: int
) -> ManufacturerThreadOut:
    role = thread.party_role(company_id) or "buyer"
    other_id = (
        thread.manufacturer_company_id
        if role == "buyer"
        else thread.buyer_company_id
    )
    other = db.get(Company, other_id)
    return ManufacturerThreadOut(
        id=thread.id,
        buyer_company_id=thread.buyer_company_id,
        manufacturer_company_id=thread.manufacturer_company_id,
        counterparty_name=(
            (other.short_name or other.legal_name or other.tax_id) if other else None
        ),
        my_role=role,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _message_out(message: ManufacturerMessage) -> ManufacturerMessageOut:
    return ManufacturerMessageOut(
        id=message.id,
        thread_id=message.thread_id,
        author_account_id=message.author_account_id,
        author_company_id=message.author_company_id,
        body=message.body,
        file_name=message.file_name,
        has_file=message.file_storage_path is not None,
        created_at=message.created_at,
    )


@router.get("", response_model=ManufacturerListOut, summary="Manufacturers directory")
def list_manufacturers(
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ManufacturerListOut:
    """GET /portal/manufacturers — verified factories with confirmed manufacturer role."""
    _ = account
    items, total = manufacturer_service.list_manufacturers(
        db, q=q, limit=limit, offset=offset
    )
    return ManufacturerListOut(
        items=[_card(db, c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/rfqs",
    response_model=list[FactoryRfqOut],
    summary="Factory RFQs for my company",
)
def list_my_factory_rfqs(
    company_id: int = Query(...),
    side: str = Query(default="sent", pattern="^(sent|incoming)$"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[FactoryRfqOut]:
    company = _company_or_404(db, account, company_id)
    return [
        _rfq_out(db, rfq)
        for rfq in manufacturer_service.list_factory_rfqs_for(
            db, company.id, side=side
        )
    ]


@router.get("/rfqs/{rfq_id}", response_model=FactoryRfqOut, summary="Factory RFQ detail")
def get_factory_rfq(
    rfq_id: int,
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> FactoryRfqOut:
    from app.services import company_service

    try:
        rfq = manufacturer_service.get_factory_rfq_for(db, account, rfq_id, company_id)
    except manufacturer_service.NotManufacturerParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found"
        ) from exc
    except company_service.CompanyNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        ) from exc
    return _rfq_out(db, rfq)


@router.post(
    "/rfqs/{rfq_id}/documents",
    response_model=FactoryRfqDocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a factory-RFQ document",
)
async def upload_factory_rfq_document(
    rfq_id: int,
    company_id: int = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> FactoryRfqDocumentOut:
    try:
        doc_kind = FactoryRfqDocumentKind(kind)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_kind"
        ) from exc

    try:
        rfq = manufacturer_service.get_factory_rfq_for(db, account, rfq_id, company_id)
    except manufacturer_service.NotManufacturerParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found"
        ) from exc

    if rfq.buyer_company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="buyer_only"
        )

    content = await file.read()
    try:
        doc = manufacturer_service.add_factory_rfq_document(
            db, rfq, kind=doc_kind, content=content, filename=file.filename or "upload"
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)


@router.get(
    "/threads",
    response_model=list[ManufacturerThreadOut],
    summary="My manufacturer chat threads",
)
def list_threads(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[ManufacturerThreadOut]:
    company = _company_or_404(db, account, company_id)
    return [
        _thread_out(db, thread, company_id=company.id)
        for thread in manufacturer_service.list_threads_for(db, company.id)
    ]


@router.get(
    "/threads/{thread_id}/messages",
    response_model=ManufacturerMessagePageOut,
    summary="Manufacturer chat messages",
)
def list_thread_messages(
    thread_id: int,
    company_id: int = Query(...),
    after_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ManufacturerMessagePageOut:
    try:
        thread = manufacturer_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except manufacturer_service.NotManufacturerParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc

    items = manufacturer_service.list_messages(
        db, thread, after_id=after_id, limit=limit
    )
    return ManufacturerMessagePageOut(
        items=[_message_out(m) for m in items],
        last_id=items[-1].id if items else None,
    )


@router.post(
    "/threads/{thread_id}/messages",
    response_model=ManufacturerMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Post a manufacturer chat message",
)
async def post_thread_message(
    thread_id: int,
    company_id: int = Form(...),
    body: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ManufacturerMessageOut:
    try:
        thread = manufacturer_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except manufacturer_service.NotManufacturerParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc

    content: bytes | None = None
    filename: str | None = None
    if file is not None and file.filename:
        content = await file.read()
        filename = file.filename

    try:
        message = manufacturer_service.post_message(
            db,
            thread,
            account,
            body,
            file_content=content,
            file_name=filename,
            company_id=company_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    db.refresh(message)
    return _message_out(message)


@router.get(
    "/threads/{thread_id}/messages/{message_id}/file",
    summary="Presigned URL for a chat attachment",
)
def get_message_file(
    thread_id: int,
    message_id: int,
    company_id: int = Query(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> dict[str, str]:
    try:
        thread = manufacturer_service.get_thread_for(
            db, account, thread_id, company_id
        )
    except manufacturer_service.NotManufacturerParticipant as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        ) from exc

    message = (
        db.query(ManufacturerMessage)
        .filter(
            ManufacturerMessage.id == message_id,
            ManufacturerMessage.thread_id == thread.id,
        )
        .first()
    )
    if message is None or not message.file_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return {"url": storage_service.presign_object(message.file_storage_path)}


@router.post(
    "/{manufacturer_id}/threads",
    response_model=ManufacturerThreadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Open or get a chat thread with a manufacturer",
)
def open_thread(
    manufacturer_id: int,
    body: ManufacturerThreadOpenIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ManufacturerThreadOut:
    buyer = _company_or_404(db, account, body.company_id)
    _require_business_role(buyer, company_service.BUYER_CAPABLE_ROLES)
    try:
        manufacturer = manufacturer_service.get_verified_manufacturer(
            db, manufacturer_id
        )
        thread = manufacturer_service.open_or_get_thread(
            db, buyer=buyer, manufacturer=manufacturer, account=account
        )
    except manufacturer_service.ManufacturerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Manufacturer not found"
        ) from exc
    except manufacturer_service.SelfManufacturer as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="self_manufacturer"
        ) from exc
    db.commit()
    db.refresh(thread)
    return _thread_out(db, thread, company_id=buyer.id)


@router.post(
    "/{manufacturer_id}/rfqs",
    response_model=FactoryRfqOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a factory RFQ",
)
def create_factory_rfq(
    manufacturer_id: int,
    body: FactoryRfqCreateIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> FactoryRfqOut:
    buyer = _company_or_404(db, account, body.company_id)
    _require_business_role(buyer, company_service.BUYER_CAPABLE_ROLES)
    try:
        manufacturer = manufacturer_service.get_verified_manufacturer(
            db, manufacturer_id
        )
    except manufacturer_service.ManufacturerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Manufacturer not found"
        ) from exc

    offer = offer_service.get_catalog_offer(db, body.offer_id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    try:
        rfq = manufacturer_service.create_factory_rfq(
            db,
            buyer=buyer,
            manufacturer=manufacturer,
            account=account,
            offer=offer,
            quantity=body.quantity,
            qty_unit=body.qty_unit or "MT",
            target_price=body.target_price,
            currency=body.currency or "USD",
            incoterms=body.incoterms,
            destination_port=body.destination_port,
            desired_delivery_date=body.desired_delivery_date,
            payment_method=body.payment_method,
            offer_validity=body.offer_validity,
            performance_guarantee=body.performance_guarantee,
            inspection_requirement=body.inspection_requirement,
            additional_requirements=body.additional_requirements,
            contact_name=body.contact_name,
            contact_position=body.contact_position,
            contact_email=body.contact_email,
            contact_phone=body.contact_phone,
            contact_telegram=body.contact_telegram,
        )
    except manufacturer_service.SelfManufacturer as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="self_manufacturer"
        ) from exc
    except manufacturer_service.OfferNotOnManufacturer as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="offer_not_on_manufacturer",
        ) from exc

    db.commit()
    db.refresh(rfq)
    rfq = manufacturer_service.get_factory_rfq_for(db, account, rfq.id, buyer.id)
    return _rfq_out(db, rfq)
