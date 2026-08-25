"""ИКПУ lookup for the offer form (P7.a Stage 2 — W9). Under /api/v1.

Every Didox document line needs an **ИКПУ** (`CatalogCode`) and a package code, and
a wrong one is a tax error on a document that reaches soliq. So the code is chosen
ONCE, by the seller, on their own offer — not re-answered per contract by whoever
happens to be drafting it — and cached on `seller_offers`.

All three endpoints need the acting company's `user-key`, which is why the picker's
empty state IS the Didox session gate: there is nothing to search without one.

**Known upstream outage.** On the test contour `/v1/profile/productClassCodes`
answers `422 {"success": false, "error": "cURL error 6: Could not resolve host:
gnk-gw.didox77.uz …"}` — their ИКПУ gateway, not our request. It surfaces here as
`503 didox_ikpu_unavailable` rather than as an empty result list, because an empty
list reads as "no such code exists" and would have the seller inventing one.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.portal.deps import company_or_404
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.accounts.models import UserAccount
from app.domains.edi import onboarding, session
from app.domains.marketplace.portal_market_schemas import IkpuOut, IkpuPackageOut
from app.integrations.didox import DidoxError, ProviderUnavailable, get_didox_client

router = APIRouter(prefix="/portal", tags=["portal-ikpu"])

#: Their gateway failing is an outage, not an answer about our search.
#:
#: Both shapes are RECORDED LIVE, hours apart, from the same endpoint:
#:   `cURL error 6: Could not resolve host: gnk-gw.didox77.uz …`
#:   `Failed to get class codes by tin`
#: The second one carries no hint that it is upstream — it reads like a rejection
#: of our request — which is exactly why this list exists rather than a check for
#: "curl". `/v1/profile` fails the same way ("Failed to get Phis By Tin Info info
#: from soliq"), so `failed to get` is their house style for "our dependency died".
_UPSTREAM_MARKERS = ("could not resolve host", "curl error", "failed to get")


def _provider_error(exc: DidoxError) -> HTTPException:
    if any(marker in exc.message.lower() for marker in _UPSTREAM_MARKERS):
        # Their ИКПУ gateway is down. An empty list here would read as "no such
        # code", and a seller would work around it by typing something plausible.
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_ikpu_unavailable"
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": "didox_rejected", "message": exc.message},
    )


def _session_or_409(
    db: Session, account: UserAccount, redis_client: redis.Redis, company_id: int  # type: ignore[type-arg]
) -> tuple[str, str]:
    """(user_key, tax_id) for the acting company, or the 409 the picker expects."""
    company = company_or_404(db, account, company_id)
    try:
        onboarding.assert_live(db)
    except onboarding.ChannelDisabled as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="didox_disabled") from exc
    try:
        return session.require_user_key(redis_client, company), company.tax_id
    except session.UserKeyRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="didox_session_required"
        ) from exc


@router.get("/ikpu/search", response_model=list[IkpuOut])
def search_ikpu(
    company_id: int = Query(...),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> list[IkpuOut]:
    """Search ИКПУ codes, each with its packages and the ЭСФ `Origin`.

    Whether the search covers the whole tasnif directory or only codes already
    bound to this company is UNSETTLED — Didox's docs describe the same URL both
    ways and their gateway is down on the test contour, so it could not be
    confirmed. If it turns out to be per-company, this endpoint keeps its shape
    and `bind` simply becomes a prerequisite rather than a convenience.
    """
    user_key, _ = _session_or_409(db, account, redis_client, company_id)
    try:
        rows = get_didox_client().product_class_codes(search=q, page=page, user_key=user_key)
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc
    return [
        IkpuOut(
            class_code=row.class_code,
            name=row.name,
            origin_id=row.origin_id,
            origin_name=row.origin_name,
            use_package=row.use_package,
            packages=[IkpuPackageOut(code=code, name=name) for code, name in row.packages],
        )
        for row in rows
    ]


@router.get("/companies/{company_id}/ikpu/{class_code}/packages", response_model=list[IkpuPackageOut])
def ikpu_packages(
    company_id: int,
    class_code: str,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> list[IkpuPackageOut]:
    """Packages for one ИКПУ. Their `lang` argument is ignored — always Russian."""
    user_key, tax_id = _session_or_409(db, account, redis_client, company_id)
    try:
        packages = get_didox_client().class_packages(tax_id, class_code, user_key=user_key)
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc
    return [IkpuPackageOut(code=code, name=name) for code, name in packages]


@router.post("/companies/{company_id}/ikpu/{class_code}/bind", status_code=status.HTTP_204_NO_CONTENT)
def bind_ikpu(
    company_id: int,
    class_code: str,
    db: Session = Depends(get_db),
    account: UserAccount = Depends(get_current_account),
    redis_client: redis.Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> None:
    """Attach an ИКПУ to the company's Didox profile.

    Separate from storing it on the offer: the offer records what WE will put on a
    document, this tells Didox the company deals in it. A seller can legitimately
    do the first without the second, so a failure here does not block the offer.
    """
    user_key, _ = _session_or_409(db, account, redis_client, company_id)
    try:
        get_didox_client().bind_product_class(class_code, user_key=user_key)
    except DidoxError as exc:
        raise _provider_error(exc) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="didox_unavailable"
        ) from exc
