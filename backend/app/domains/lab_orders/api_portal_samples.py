"""Portal sample-request endpoints (P6 W3 — T3.2, FR-L3). Under /api/v1/portal.

A buyer asks for material to hold; the seller ships it; the buyer confirms it
arrived. Both sides use the same transition route — which party may make which
move is `sample_service._ACTOR_RULES`, not five hand-written verb routes each
with its own chance to forget the check.

Everything is company-scoped through membership: a request the caller's company
is not a party to is a 404, the same answer a non-member gets anywhere in the
portal.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404, require_business_role
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.accounts.models import UserAccount
from app.domains.companies import service as company_service
from app.domains.companies.models import Company
from app.domains.deals import service as deal_service
from app.domains.lab_orders import letters
from app.domains.lab_orders import samples as sample_service
from app.domains.lab_orders.models import SampleRequest
from app.domains.lab_orders.schemas import (
    SampleDealIn,
    SampleDealOut,
    SampleLetterChallengeOut,
    SampleLetterOut,
    SampleLetterSignIn,
    SampleRequestIn,
    SampleRequestOut,
    SampleTransitionIn,
)
from app.domains.marketplace import service as offer_service
from app.integrations.eimzo import ProviderUnavailable as EimzoUnavailable
from app.models.enums import SampleRequestStatus
from app.services import notification_service, storage_service


def _letter_out(sample: SampleRequest) -> SampleLetterOut:
    return SampleLetterOut(
        number=sample.letter_number,
        sha256=sample.letter_sha256,
        signed_at=sample.letter_signed_at,
        terms=sample.letter_terms_snapshot,
        required=True,
    )


router = APIRouter(prefix="/portal", tags=["portal-samples"])


def _out(db: Session, sample: SampleRequest, *, company_id: int) -> SampleRequestOut:
    role = sample_service.acting_role(sample, company_id)
    other_id = (
        sample.buyer_company_id if role == "seller" else sample.seller_company_id
    )
    other = db.get(Company, other_id)
    offer = sample.offer
    return SampleRequestOut(
        id=sample.id,
        offer_id=sample.offer_id,
        offer_title=(offer.product_text or offer.grade_text) if offer else None,
        status=str(sample.status),
        buyer_company_id=sample.buyer_company_id,
        seller_company_id=sample.seller_company_id,
        counterparty_name=(
            (other.short_name or other.legal_name or other.tax_id) if other else None
        ),
        my_role=role,
        available_transitions=[
            str(s) for s in sample_service.available_transitions(sample.status, role)
        ],
        qty=sample.qty,
        delivery_address=sample.delivery_address,
        courier=sample.courier,
        tracking_ref=sample.tracking_ref,
        decline_reason=sample.decline_reason,
        accepted_at=sample.accepted_at,
        sent_at=sample.sent_at,
        received_at=sample.received_at,
        created_at=sample.created_at,
        letter_required=(
            sample.status == SampleRequestStatus.pending_letter
            or sample.letter_signed_at is not None
        ),
        letter_signed_at=sample.letter_signed_at,
        letter_number=sample.letter_number,
    )


@router.get("/companies/{company_id}/samples", response_model=list[SampleRequestOut])
def list_samples(
    company_id: int,
    side: str = Query(default="incoming", pattern="^(incoming|sent)$"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[SampleRequestOut]:
    """`incoming` — requests to answer; `sent` — requests we made."""
    company = company_or_404(db, account, company_id)
    return [
        _out(db, sample, company_id=company.id)
        for sample in sample_service.list_for_company(db, company.id, side=side)
    ]


@router.post(
    "/market/offers/{offer_id}/samples",
    response_model=SampleRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def request_sample(
    offer_id: int,
    body: SampleRequestIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SampleRequestOut:
    """Ask the seller for a sample of a public offer."""
    company = company_or_404(db, account, body.company_id)
    require_business_role(company, company_service.BUYER_CAPABLE_ROLES)
    offer = offer_service.get_catalog_offer(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    try:
        sample = sample_service.request(
            db,
            offer=offer,
            buyer_company=company,
            account=account,
            delivery_address=body.delivery_address,
            qty=body.qty,
        )
    except sample_service.SamplesNotAvailable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "samples_not_available"},
        ) from exc
    except sample_service.OwnOfferSample as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "own_offer"},
        ) from exc
    except sample_service.SampleRequestExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "already_requested"}
        ) from exc

    db.commit()
    db.refresh(sample)
    return _out(db, sample, company_id=company.id)


@router.post("/samples/{sample_id}/transition", response_model=SampleRequestOut)
def transition_sample(
    sample_id: int,
    body: SampleTransitionIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SampleRequestOut:
    """Accept, decline, ship, receive or reject — whichever your side may do.

    Refusals are separately coded so the portal can say what is wrong:
    `invalid_transition`, `not_your_move`, `reason_required`,
    `shipment_details_required`.
    """
    company = company_or_404(db, account, body.company_id)
    sample = db.get(SampleRequest, sample_id)
    if sample is None or sample.party_role(company.id) is None:
        # 404 for a request the caller's company is not part of: the same answer
        # a non-member gets, so probing an id reveals nothing.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if body.to_status not in {s.value for s in SampleRequestStatus}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_status"
        )

    try:
        sample_service.transition(
            db,
            sample,
            SampleRequestStatus(body.to_status),
            acting_company_id=company.id,
            reason=body.reason,
            qty=body.qty,
            courier=body.courier,
            tracking_ref=body.tracking_ref,
        )
    except sample_service.ActorNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "not_your_move"}
        ) from exc
    except sample_service.InvalidSampleTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "invalid_transition"}
        ) from exc
    except sample_service.ReasonRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "reason_required"},
        ) from exc
    except sample_service.ShipmentDetailsRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "shipment_details_required"},
        ) from exc

    db.commit()
    db.refresh(sample)
    return _out(db, sample, company_id=company.id)

@router.post(
    "/samples/{sample_id}/deal",
    response_model=SampleDealOut,
    status_code=status.HTTP_201_CREATED,
)
def open_deal_from_sample(
    sample_id: int,
    body: SampleDealIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SampleDealOut:
    """Turn a RECEIVED sample into a deal — the buyer's decision, explicitly made.

    Not automatic on receipt: a sample that arrived says nothing about price or
    quantity, and a deal needs an amount. It is also where "the material suits me"
    stops being a lab result and becomes a commercial commitment, which is exactly
    the kind of thing a person should have to click.
    """
    sample = db.get(SampleRequest, sample_id)
    if sample is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found")
    try:
        buyer = company_service.get_company_for(db, account, sample.buyer_company_id)
    except company_service.CompanyNotFound as exc:
        # Buyer-only, and a seller peeking learns nothing they did not already know.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found") from exc

    try:
        deal = deal_service.open_deal_from_sample(
            db, sample, account, amount=body.amount, currency=body.currency
        )
    except deal_service.DealAlreadyOpen as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="deal_already_open") from exc
    except deal_service.DealRequiresCompany as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="sample_not_received"
        ) from exc
    except deal_service.CompanyNotVerified as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="company_not_verified"
        ) from exc
    db.commit()
    return SampleDealOut(deal_id=deal.id, number=deal.number, buyer_company_id=buyer.id)


# ── Commitment letter (P7.a W8) ───────────────────────────────────────────────


def _buyer_or_404(db: Session, account: UserAccount, sample: SampleRequest) -> Company:
    """The letter is the BUYER's undertaking, so only the buyer may render or sign it."""
    try:
        return company_service.get_company_for(db, account, sample.buyer_company_id)
    except company_service.CompanyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found") from exc


def _sample_or_404(db: Session, sample_id: int) -> SampleRequest:
    sample = db.get(SampleRequest, sample_id)
    if sample is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found")
    return sample


@router.get("/samples/{sample_id}/letter", response_model=SampleLetterOut)
def get_sample_letter(
    sample_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SampleLetterOut:
    """Render (or re-render) the letter and return its metadata.

    Idempotent while unsigned; refuses once signed, because the PDF is what the
    signature covers and re-rendering would leave a signature over bytes nobody
    agreed to. Visible to BOTH parties — the seller needs to read what the buyer
    undertook — but only the buyer can cause a render.
    """
    sample = _sample_or_404(db, sample_id)
    try:
        company_service.get_company_for(db, account, sample.buyer_company_id)
        is_buyer = True
    except company_service.CompanyNotFound:
        is_buyer = False
        try:
            company_service.get_company_for(db, account, sample.seller_company_id)
        except company_service.CompanyNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found") from exc

    if is_buyer and sample.letter_signed_at is None:
        try:
            letters.render_letter(db, sample)
            db.commit()
        except letters.LetterNotRequired as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="letter_not_required"
            ) from exc
        except letters.TemplateMissing as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="letter_template_missing"
            ) from exc
    return _letter_out(sample)


@router.get("/samples/{sample_id}/letter/document")
def sample_letter_document(
    sample_id: int,
    as_: str = Query(default="redirect", alias="as"),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> Response:
    """The letter PDF, presigned. Mirrors the contract document route.

    Visible to BOTH parties — a commitment the seller cannot read is not evidence
    of anything — but neither side can cause a RENDER here; that stays on the
    buyer-only GET above, so a seller opening the letter can never change the
    bytes a signature is about to cover.
    """
    sample = _sample_or_404(db, sample_id)
    for company_id in (sample.buyer_company_id, sample.seller_company_id):
        try:
            company_service.get_company_for(db, account, company_id)
            break
        except company_service.CompanyNotFound:
            continue
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found")

    if not sample.letter_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No letter")
    url = storage_service.presign_object(sample.letter_storage_path, ttl=600)
    if as_ == "url":
        return JSONResponse({"url": url})
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post("/samples/{sample_id}/letter/challenge", response_model=SampleLetterChallengeOut)
def sample_letter_challenge(
    sample_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> SampleLetterChallengeOut:
    """A single-use challenge bound to the letter's sha256."""
    sample = _sample_or_404(db, sample_id)
    buyer = _buyer_or_404(db, account, sample)
    try:
        challenge = letters.issue_challenge(redis_client, sample, buyer.id)
    except letters.LetterAlreadySigned as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_signed") from exc
    except letters.ChallengeExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="letter_not_rendered"
        ) from exc
    return SampleLetterChallengeOut(challenge=challenge)


@router.post("/samples/{sample_id}/letter/sign", response_model=SampleRequestOut)
def sign_sample_letter(
    sample_id: int,
    body: SampleLetterSignIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> SampleRequestOut:
    """Sign the letter — which is what releases the request to the seller."""
    sample = _sample_or_404(db, sample_id)
    buyer = _buyer_or_404(db, account, sample)
    try:
        letters.sign(db, redis_client, sample, buyer, account, body.pkcs7)
    except letters.LetterAlreadySigned as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_signed") from exc
    except letters.ChallengeExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="challenge_expired"
        ) from exc
    except letters.CertCompanyMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "cert_company_mismatch",
                "cert_inn": exc.cert_inn_masked,
                "company_inn": exc.company_inn_masked,
            },
        ) from exc
    except letters.SignatureVerificationFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "signature_failed", "reason": exc.reason},
        ) from exc
    except EimzoUnavailable as exc:
        # The sidecar is down; the buyer can try again. Nothing was consumed —
        # the challenge is gone, but re-issuing one is a click.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="eimzo_unavailable"
        ) from exc

    # The letter is signed, so the seller now has a real request to answer.
    sample_service._notify(  # noqa: SLF001 — same package, one notification path
        db, sample, notification_service.KIND_SAMPLE_REQUEST_NEW, to="seller"
    )
    db.commit()
    return _out(db, sample, company_id=buyer.id)
