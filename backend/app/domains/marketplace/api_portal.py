"""Portal company-offer endpoints (R1 W5 — T5.2). Under /api/v1/portal.

A verified company publishes offers that flow through the EXISTING moderation
machine (pending_moderation → approved/rejected). All routes require a portal
account + company membership (non-member → 404). Publishing from an unverified
company → 403 with a typed `{code: "company_not_verified"}` body.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404, rate_limited, require_business_role
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.marketplace import service as offer_service
from app.domains.marketplace.models import SellerOffer, SellerOfferFile
from app.models.accounts import UserAccount
from app.models.enums import OfferFileKind, SellerOfferStatus
from app.schemas.portal_company import CompanyOfferIn, CompanyOfferOut
from app.services import company_service, lab_service, rate_limit, storage_service

router = APIRouter(prefix="/portal/companies", tags=["portal-offers"])


def _offer_or_404(db: Session, company_id: int, offer_id: int) -> SellerOffer:
    offer = (
        db.query(SellerOffer)
        .filter(SellerOffer.id == offer_id, SellerOffer.company_id == company_id)
        .first()
    )
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer


@router.get("/{company_id}/offers", response_model=list[CompanyOfferOut])
def list_offers(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[SellerOffer]:
    company = company_or_404(db, account, company_id)
    return offer_service.list_company_offers(db, company.id)


@router.post("/{company_id}/offers", response_model=CompanyOfferOut, status_code=status.HTTP_201_CREATED)
def create_offer(
    company_id: int,
    body: CompanyOfferIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> SellerOffer:
    company = company_or_404(db, account, company_id)
    try:
        rate_limit.enforce_daily(
            redis_client, "offer_create", company.id, rate_limit.OFFER_CREATE_PER_DAY
        )
    except rate_limit.RateLimited as exc:
        raise rate_limited(exc) from exc
    try:
        offer = offer_service.create_company_offer(db, company, account, body)
    except offer_service.CompanyNotVerified as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": "company_not_verified"}
        ) from exc
    except company_service.RoleNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": "role_not_allowed"}
        ) from exc
    db.commit()
    # A compliance-held offer is saved as a draft, not queued: there is nothing
    # for the team to moderate until the seller supplies what is missing.
    if offer.status == SellerOfferStatus.pending_moderation:
        offer_service.enqueue_offer_group_notify(offer.id)
    return offer


@router.get("/{company_id}/offers/{offer_id}", response_model=CompanyOfferOut)
def get_offer(
    company_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    company = company_or_404(db, account, company_id)
    return _offer_or_404(db, company.id, offer_id)


@router.patch("/{company_id}/offers/{offer_id}", response_model=CompanyOfferOut)
def update_offer(
    company_id: int,
    offer_id: int,
    body: CompanyOfferIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    company = company_or_404(db, account, company_id)
    offer = _offer_or_404(db, company.id, offer_id)
    require_business_role(company, company_service.SELLER_ROLES)
    offer, requeued = offer_service.update_company_offer(db, offer, body)
    db.commit()
    if requeued and offer.status == SellerOfferStatus.pending_moderation:
        offer_service.enqueue_offer_group_notify(offer.id, edited=True)
    return offer


@router.post("/{company_id}/offers/{offer_id}/archive", response_model=CompanyOfferOut)
def archive_offer(
    company_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    company = company_or_404(db, account, company_id)
    offer = _offer_or_404(db, company.id, offer_id)
    offer.status = SellerOfferStatus.archived
    offer.published_at = None
    db.commit()
    return offer


@router.post("/{company_id}/offers/{offer_id}/files", response_model=CompanyOfferOut, status_code=status.HTTP_201_CREATED)
async def upload_offer_file(
    company_id: int,
    offer_id: int,
    kind: str = Form("image"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    """Attach a photo (or document) to an offer.

    Photos: ≤ 8 per offer, JPEG/PNG, ≤ 10 MB (FR-M2). Adding one to a live offer
    re-enters moderation, since photos are part of what was approved.

    A `lab_passport` (P6) must be a PDF and also re-enters moderation: unlike an
    SDS, which only feeds the compliance verdict, it puts a public badge on the
    market card, so it is part of what was approved too.
    """
    company = company_or_404(db, account, company_id)
    offer = _offer_or_404(db, company.id, offer_id)
    try:
        file_kind = OfferFileKind(kind)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown file kind") from exc

    # The photo cap counts images only — a TDS never consumes a photo slot.
    if (
        file_kind == OfferFileKind.image
        and offer_service.count_offer_images(db, offer.id) >= storage_service.MAX_OFFER_IMAGES
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="too_many_files"
        )

    content = await file.read()

    # Detect the type BEFORE writing anything: `kind=image` must really be an image
    # (the generic allow-list also passes PDFs and spreadsheets, which are valid
    # documents but not product photos). Checking after the upload would leave an
    # orphaned object in S3 for every rejected file.
    try:
        mime = storage_service.validate_upload(content, file.filename or "upload")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if file_kind == OfferFileKind.image and mime not in storage_service.IMAGE_MIMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_file_type"
        )
    # A laboratory passport is a document with a badge attached to it. A photo of
    # one is not something a buyer can read, and not something staff can check.
    if file_kind == OfferFileKind.lab_passport and mime != lab_service.RESULT_MIME:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_file_type"
        )

    try:
        storage_service.upload_offer_file(
            db, offer.id, content, file.filename or "upload", file_kind
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    requeued = False
    if file_kind in (OfferFileKind.image, OfferFileKind.lab_passport):
        requeued = offer_service.requeue_for_photo_change(db, offer)
    else:
        # A compliance document is the thing a held draft was waiting for
        # (documents can only be attached once the offer row exists).
        requeued = offer_service.recheck_compliance_after_files(db, offer)
    db.commit()
    db.refresh(offer)
    if requeued:
        offer_service.enqueue_offer_group_notify(offer.id, edited=True)
    return offer


@router.get(
    "/{company_id}/offers/{offer_id}/files/{file_id}",
    summary="Offer file bytes (owner-scoped)",
)
def get_offer_file(
    company_id: int,
    offer_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    """Serve an offer file to its own company, at ANY offer status.

    The public catalog endpoint only serves files of *approved* offers, so without
    this a seller could not see the photos on their own draft. Company-scoped, and
    404 (not 403) for everyone else — consistent with the rest of the portal.
    """
    company = company_or_404(db, account, company_id)
    offer = _offer_or_404(db, company.id, offer_id)
    f = (
        db.query(SellerOfferFile)
        .filter(SellerOfferFile.id == file_id, SellerOfferFile.offer_id == offer.id)
        .first()
    )
    if f is None or f.storage_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from app.core.config import settings  # noqa: PLC0415
    from app.core.storage import s3_client  # noqa: PLC0415

    obj = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=f.storage_path)  # type: ignore[attr-defined]
    body: bytes = obj["Body"].read()
    return Response(content=body, media_type=f.mime_type or "application/octet-stream")


@router.delete("/{company_id}/offers/{offer_id}/files/{file_id}", response_model=CompanyOfferOut)
def delete_offer_file(
    company_id: int,
    offer_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SellerOffer:
    """Detach a file. Removing a photo from a live offer re-enters moderation.

    A passport that a platform lab order produced cannot be removed at all (409):
    it is the evidence behind the "Laboratory Verified" badge, staff uploaded it,
    and deleting it would leave the badge standing on nothing. Removing a
    self-uploaded passport is fine — and takes the verification with it if it was
    the last one.

    Returns the updated offer so the client re-renders the gallery (and the promoted
    cover) from one response.
    """
    company = company_or_404(db, account, company_id)
    offer = _offer_or_404(db, company.id, offer_id)
    f = (
        db.query(SellerOfferFile)
        .filter(SellerOfferFile.id == file_id, SellerOfferFile.offer_id == offer.id)
        .first()
    )
    if f is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    try:
        lab_service.assert_result_unlocked(db, f.id)
    except lab_service.LabResultLocked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "lab_result_locked"}
        ) from exc

    visible_change = f.kind in (OfferFileKind.image, OfferFileKind.lab_passport)
    storage_path = f.storage_path
    db.delete(f)
    db.flush()
    lab_service.clear_lab_verification(db, offer)

    requeued = (
        offer_service.requeue_for_photo_change(db, offer) if visible_change else False
    )
    db.commit()
    if storage_path:
        storage_service.discard_object(storage_path, context="offer_file_delete")
    db.refresh(offer)
    if requeued:
        offer_service.enqueue_offer_group_notify(offer.id, edited=True)
    return offer
