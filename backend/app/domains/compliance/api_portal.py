"""Portal compliance views (P5 W3 — T3.4, W4 — T4.2). Under /api/v1/portal.

Company-scoped: what an offer still needs before it can be published, which
licences the company holds, and the AI substance hint. The first two are what
the "почему не публикуется" panel is built from — a seller who cannot see the
requirement can only guess.

Non-members get 404 (never 403), consistent with the rest of the portal.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404, rate_limited
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.compliance import licenses as company_license_service
from app.domains.compliance import substance_ai as substance_ai_service
from app.domains.compliance.schemas import CompanyLicenseOut, ComplianceOut
from app.domains.compliance.substance_match_schemas import (
    SubstanceSuggestionOut,
    SuggestIn,
    SuggestionDecisionIn,
)
from app.domains.compliance.substance_schemas import SubstanceBrief
from app.domains.marketplace import compliance as offer_compliance_service
from app.domains.marketplace.models import SellerOffer
from app.models.accounts import UserAccount
from app.services import rate_limit

router = APIRouter(prefix="/portal/companies", tags=["portal-compliance"])


@router.get(
    "/{company_id}/licenses",
    response_model=list[CompanyLicenseOut],
    summary="Licences this company holds",
)
def my_licenses(
    company_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> list[CompanyLicenseOut]:
    """Read-only: licences are registered by staff from an accepted document."""
    company = company_or_404(db, account, company_id)
    return company_license_service.list_for(db, company.id)  # type: ignore[return-value]


@router.get(
    "/{company_id}/offers/{offer_id}/compliance",
    response_model=ComplianceOut,
    summary="What this offer still needs to be published",
)
def offer_compliance(
    company_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> ComplianceOut:
    company = company_or_404(db, account, company_id)
    offer = (
        db.query(SellerOffer)
        .filter(SellerOffer.id == offer_id, SellerOffer.company_id == company.id)
        .first()
    )
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer_compliance_service.verdict_out(db, offer)


# ── AI substance hint (P5 W4 — T4.2, FR-C3) ───────────────────────────────────


def _out(suggestion) -> SubstanceSuggestionOut:  # noqa: ANN001
    """Serialize a hint with the registry row it resolved to (if any)."""
    payload = SubstanceSuggestionOut.model_validate(suggestion)
    if suggestion.substance_id is not None and suggestion.substance is not None:
        payload = payload.model_copy(
            update={"substance": SubstanceBrief.model_validate(suggestion.substance)}
        )
    return payload


@router.post(
    "/{company_id}/substance-suggestions",
    response_model=SubstanceSuggestionOut,
    summary="Ask the AI which substance this offer text is about",
)
def suggest_substance(
    company_id: int,
    body: SuggestIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> SubstanceSuggestionOut | Response:
    """A suggestion, never a decision — nothing is written onto the offer.

    204 when there is no hint to give (the feature is off, or the daily token
    budget is spent): the form has to be able to tell "no hint" from "the hint
    failed", and neither is an error the seller can act on.
    """
    company = company_or_404(db, account, company_id)
    try:
        rate_limit.enforce_daily(
            redis_client, "substance_suggest", company.id, rate_limit.SUBSTANCE_SUGGEST_PER_DAY
        )
    except rate_limit.RateLimited as exc:
        raise rate_limited(exc) from exc

    suggestion = substance_ai_service.suggest(
        db, text=body.text, company_id=company.id, offer_id=body.offer_id
    )
    if suggestion is None:
        db.rollback()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    db.commit()
    db.refresh(suggestion)
    return _out(suggestion)


@router.post(
    "/{company_id}/substance-suggestions/{suggestion_id}/decision",
    response_model=SubstanceSuggestionOut,
    summary="Confirm or reject an AI substance hint",
)
def decide_substance_suggestion(
    company_id: int,
    suggestion_id: int,
    body: SuggestionDecisionIn,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
) -> SubstanceSuggestionOut:
    """The seller's answer (FR-C3). Rejection is recorded, not discarded."""
    company = company_or_404(db, account, company_id)
    suggestion = substance_ai_service.get_for_company(db, suggestion_id, company.id)
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    substance_ai_service.decide(
        db, suggestion, accepted=body.accepted, account_id=account.id
    )
    db.commit()
    db.refresh(suggestion)
    return _out(suggestion)
