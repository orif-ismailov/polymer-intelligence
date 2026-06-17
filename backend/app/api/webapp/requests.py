"""
/webapp/requests — POST create, GET list, GET detail for client purchase requests.

Every handler authenticates via get_current_client (initData HMAC from 03-01)
and scopes data to the verified client only (IDOR-safe).

Security:
  T-03-07: IDOR — GET /requests and GET /requests/{id} filter by client.id
           from the verified initData dependency, NEVER by a value from the
           request body or query string.
  T-03-08: Spoofing — create_request service takes the Client ORM object from
           the dep; no client_id field in the body schema (T-03-06 equivalent).
  T-03-03: 401 on any initData failure (generic, no hint of which field failed).
  T-03-09: Status machine enforced in request_service; ValueError → 422.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.models.requests import Client, Request
from app.schemas.webapp import RequestCreate, RequestDetailOut, RequestOut
from app.services import request_service

router = APIRouter(prefix="/webapp", tags=["webapp"])


@router.post(
    "/requests",
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase request (client)",
)
def create_request(
    body: RequestCreate,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> RequestOut:
    """POST /webapp/requests — create a client purchase request.

    Generates a REQ-YYYY-MM-DD-NNNNN number, writes a status_history row (new),
    enqueues the notify task. Returns 201 with {id, number, status, created_at}.

    Identity comes from the verified initData dep (get_current_client), NEVER
    from the body — body has no client_id field (T-03-08 / T-03-06 equivalent).

    Raises:
        HTTP 401: missing or invalid X-Telegram-Init-Data (T-03-03).
        HTTP 422: D-02 minimum not met (no product_id, no volume, no grade or polymer).
        HTTP 422: service-level ValueError (e.g. unexpected error from number gen).
    """
    try:
        req = request_service.create_request(db=db, client=client, data=body)
        db.commit()
        return req  # type: ignore[return-value]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/requests",
    response_model=list[RequestOut],
    summary="List authenticated client's requests",
)
def list_requests(
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> list[RequestOut]:
    """GET /webapp/requests — list requests scoped to the authenticated client.

    Returns newest-first. NEVER returns requests belonging to other clients
    (identity from verified dep only — T-03-07).
    """
    # T-03-07: always scope by client.id from verified initData
    requests = (
        db.query(Request)
        .filter(Request.client_id == client.id)
        .order_by(Request.created_at.desc())
        .all()
    )
    return requests  # type: ignore[return-value]


@router.get(
    "/requests/{request_id}",
    response_model=RequestDetailOut,
    summary="Get request detail (authenticated client, own requests only)",
)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> RequestDetailOut:
    """GET /webapp/requests/{id} — detail view scoped to the calling client.

    T-03-07 IDOR guard: the WHERE clause filters on BOTH request id AND client_id.
    A request owned by another client returns 404 — indistinguishable from
    "not found" — to prevent probing (no cross-client information disclosure).

    Returns the request with all files + status_history (ordered created_at ASC).

    Raises:
        HTTP 401: missing or invalid X-Telegram-Init-Data.
        HTTP 404: request not found OR not owned by the calling client.
    """
    # T-03-07: both id AND client_id must match — intentionally opaque 404
    req: Request | None = (
        db.query(Request)
        .filter(Request.id == request_id, Request.client_id == client.id)
        .first()
    )

    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    # Build detail out — history ordered ASC for timeline display
    history = sorted(req.status_history, key=lambda h: h.created_at)
    # Return a dict that Pydantic can validate — MR-03: pass all detail fields
    return RequestDetailOut(
        id=req.id,
        number=req.number,
        status=req.status,
        created_at=req.created_at,
        product_id=req.product_id,
        grade_text=req.grade_text,
        polymer_type=req.polymer_type,
        volume=req.volume,
        volume_unit=req.volume_unit,
        target_price=req.target_price,
        currency=req.currency,
        incoterms=req.incoterms,
        destination_country=req.destination_country,
        port_or_city=req.port_or_city,
        desired_date=req.desired_date,
        validity_days=req.validity_days,
        urgency=req.urgency,
        comment=req.comment,
        files=req.files,
        history=history,
    )
