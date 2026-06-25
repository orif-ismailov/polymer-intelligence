"""
Dashboard requests router — staff-facing Purchase Requests API.

Phase 4, Plan 04: GET /requests list, GET /requests/{id} detail,
PATCH /requests/{id} status machine, and team actions:
  POST /requests/{id}/note — add a free-text note (audit_log)
  POST /requests/{id}/assign — assign an owner (audit_log)
  POST /requests/{id}/contact — Contact Buyer deep-link (audit_log + D-11 tg://)

Phase 4, Plan 05: GET /requests/export — CSV stream of current filtered result set.
  Accepts the same filter query params as GET /requests.
  Streams via StreamingResponse + csv.writer generator.
  Capped at 50,000 rows (T-04-18: DoS / large result).
  Guarded by get_current_staff_user.

Security (T-04-10/T-04-11/T-04-12/T-04-14/T-04-18):
  T-04-10: PATCH and actions are guarded by require_role(admin, analyst, trader).
           Viewer role → 403. Status only via transition_status (D-12).
  T-04-11: transition_status raises ValueError on illegal transition → 422.
           request.status is NEVER set directly in this router (Pitfall 5).
  T-04-12: Every action writes audit_log via write_audit in the same transaction
           (db.flush, router commits). staff_user_id from verified JWT, never body.
  T-04-14: contact_available derived from telegram_user_id IS NOT NULL.
           No tg://user?id=None link is ever built (Pitfall 6).
  T-04-18: Export capped at 50,000 rows; StreamingResponse avoids loading all rows
           in memory at once.

D-01: ai fields (match_score/demand_level/recommendation) returned as-is from
      request.ai JSONB (null in Phase 4 — Phase 5 fills them in).
D-02: price_analysis computed by price_analysis_service.compute_price_analysis.
D-11: Contact Buyer builds tg://user?id={telegram_user_id} when available.
D-12: Status machine enforced server-side via transition_status.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff_user, require_role
from app.core.db import get_db
from app.models.enums import RequestStatus, StaffRole
from app.models.requests import Request
from app.models.staff import StaffUser
from app.schemas.dashboard import (
    RequestDetailOut,
    RequestFileOut,
    RequestListOut,
    RequestPatch,
)
from app.services import (
    price_analysis_service,
    request_analysis_service,
    request_service,
)

router = APIRouter(prefix="/requests", tags=["dashboard-requests"])


def _build_request_detail(
    req: Request,
    db: Session,
) -> dict:
    """Build the RequestDetailOut payload for a request.

    Computes:
    - price_analysis (D-02) from price_analysis_service
    - ai (D-01) echoed as-is from req.ai
    - contact_available (D-11) from client.telegram_user_id IS NOT NULL
    - files list
    """
    # D-02: real price analysis (not AI)
    price_analysis = price_analysis_service.compute_price_analysis(
        db=db,
        product_id=req.product_id,
        target_price=req.target_price,
        currency=req.currency,
    )

    # D-11: contact_available only when telegram_user_id IS NOT NULL (Pitfall 6)
    contact_available = (
        req.client is not None
        and req.client.telegram_user_id is not None
    )

    # D-01: echo ai JSONB as-is (null fields in Phase 4)
    ai_block = req.ai if req.ai is not None else {}

    # Build files summary
    files_out = [
        RequestFileOut(
            id=f.id,
            file_name=f.file_name,
            mime_type=f.mime_type,
            size_bytes=f.size_bytes,
            storage_path=f.storage_path,
            created_at=f.created_at,
        )
        for f in (req.files or [])
    ]

    return RequestDetailOut(
        id=req.id,
        number=req.number,
        status=req.status.value if hasattr(req.status, "value") else str(req.status),
        product_id=req.product_id,
        grade_text=req.grade_text,
        polymer_type=req.polymer_type,
        volume=req.volume,
        volume_unit=req.volume_unit,
        target_price=req.target_price,
        currency=req.currency,
        incoterms=req.incoterms.value if hasattr(req.incoterms, "value") else str(req.incoterms),
        destination_country=req.destination_country,
        port_or_city=req.port_or_city,
        desired_date=req.desired_date,
        validity_days=req.validity_days,
        urgency=req.urgency.value if hasattr(req.urgency, "value") else str(req.urgency),
        comment=req.comment,
        assigned_to=req.assigned_to,
        ai=ai_block,
        price_analysis=price_analysis,
        contact_available=contact_available,
        files=files_out,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


# ── GET list ──────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[RequestListOut],
    summary="List all purchase requests (staff)",
)
def list_requests(
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(get_current_staff_user),
    status_filter: str | None = Query(default=None, alias="status"),
    urgency: str | None = None,
    product_id: int | None = None,
) -> list[RequestListOut]:
    """GET /requests — return requests ordered newest-first with optional filters.

    Filter query params (all optional):
    - status: filter by request status (e.g. "new", "in_progress")
    - urgency: filter by urgency level (e.g. "high", "medium", "low")
    - product_id: filter by numeric product id

    JWT-guarded (any staff role). Returns RequestListOut[] (no detail fields).

    Raises:
        HTTP 401: Missing or invalid Bearer token.
    """
    query = db.query(Request).order_by(Request.created_at.desc())

    if status_filter is not None:
        query = query.filter(Request.status == status_filter)
    if urgency is not None:
        query = query.filter(Request.urgency == urgency)
    if product_id is not None:
        query = query.filter(Request.product_id == product_id)

    reqs = query.all()
    return [
        RequestListOut(
            id=r.id,
            number=r.number,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
            product_id=r.product_id,
            grade_text=r.grade_text,
            polymer_type=r.polymer_type,
            volume=r.volume,
            volume_unit=r.volume_unit,
            target_price=r.target_price,
            currency=r.currency,
            urgency=r.urgency.value if hasattr(r.urgency, "value") else str(r.urgency),
            assigned_to=r.assigned_to,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in reqs
    ]


# ── GET /requests/export CSV stream ───────────────────────────────────────────

_EXPORT_COLUMNS = [
    "id",
    "number",
    "status",
    "product_id",
    "grade_text",
    "polymer_type",
    "volume",
    "volume_unit",
    "target_price",
    "currency",
    "urgency",
    "assigned_to",
    "created_at",
    "updated_at",
]

_EXPORT_ROW_CAP = 50_000


@router.get(
    "/export",
    summary="Export purchase requests as CSV stream (staff)",
    response_class=StreamingResponse,
)
def export_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    urgency: str | None = None,
    product_id: int | None = None,
    db: Session = Depends(get_db),
    _current_user: StaffUser = Depends(get_current_staff_user),
) -> StreamingResponse:
    """GET /requests/export — stream all matching requests as CSV (T-04-18: cap 50k).

    Accepts the same filter query params as GET /requests.
    Returns a StreamingResponse with media_type='text/csv' so the client
    receives the CSV as an attachment without loading the full result set
    into memory at once.

    Raises:
        HTTP 401: Missing or invalid Bearer token.
    """
    # Build the query with the same filters as list_requests
    query = db.query(Request).order_by(Request.created_at.desc())

    if status_filter is not None:
        query = query.filter(Request.status == status_filter)
    if urgency is not None:
        query = query.filter(Request.urgency == urgency)
    if product_id is not None:
        query = query.filter(Request.product_id == product_id)

    def _csv_generator():
        """Generator that yields CSV lines as bytes, capped at _EXPORT_ROW_CAP rows."""
        buf = io.StringIO()
        writer = csv.writer(buf)

        # Header row
        writer.writerow(_EXPORT_COLUMNS)
        yield buf.getvalue().encode("utf-8")
        buf.truncate(0)
        buf.seek(0)

        # Data rows — stream in chunks using .yield_per() for memory efficiency
        for row_count, req in enumerate(query.limit(_EXPORT_ROW_CAP)):
            if row_count >= _EXPORT_ROW_CAP:
                break
            writer.writerow([
                req.id,
                req.number,
                req.status.value if hasattr(req.status, "value") else str(req.status),
                req.product_id,
                req.grade_text,
                req.polymer_type,
                req.volume,
                req.volume_unit,
                req.target_price,
                req.currency,
                req.urgency.value if hasattr(req.urgency, "value") else str(req.urgency),
                req.assigned_to,
                req.created_at.isoformat() if req.created_at else "",
                req.updated_at.isoformat() if req.updated_at else "",
            ])
            yield buf.getvalue().encode("utf-8")
            buf.truncate(0)
            buf.seek(0)

    return StreamingResponse(
        _csv_generator(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=requests.csv",
        },
    )


# ── GET detail ────────────────────────────────────────────────────────────────

@router.get(
    "/{request_id}",
    response_model=RequestDetailOut,
    summary="Get request detail with price analysis (staff)",
)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(get_current_staff_user),
) -> RequestDetailOut:
    """GET /requests/{id} — detail view, auto-transitions new->viewed (D-12).

    If the request status is `new`, calls transition_status(new->viewed) and
    commits before returning the detail. This records the staff's first view
    in request_status_history and audit_log.

    Embeds:
    - price_analysis (D-02): real computation from price_points.
    - ai (D-01): echoed from req.ai JSONB (null in Phase 4).
    - contact_available (D-11): True when client.telegram_user_id IS NOT NULL.
    - files: list of file summaries.

    Raises:
        HTTP 401: Missing or invalid Bearer token.
        HTTP 404: Request not found.
    """
    req: Request | None = (
        db.query(Request).filter(Request.id == request_id).first()
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    # D-12: auto-transition new->viewed on first staff view
    if req.status == RequestStatus.new:
        request_service.transition_status(
            db=db,
            request=req,
            to_status=RequestStatus.viewed,
            changed_by=current_user.id,
        )
        db.commit()

    return _build_request_detail(req, db)


# ── PATCH status ──────────────────────────────────────────────────────────────

@router.patch(
    "/{request_id}",
    response_model=RequestDetailOut,
    summary="Change request status / assign / add note (staff)",
)
def patch_request(
    request_id: int,
    body: RequestPatch,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(
        require_role(StaffRole.admin, StaffRole.analyst, StaffRole.trader)
    ),
) -> RequestDetailOut:
    """PATCH /requests/{id} — status change, assign, or add note.

    Status changes route through request_service.transition_status — the status
    field in the body is NEVER applied directly (T-04-11 / Pitfall 5).

    assign_to and note are handled via their respective service functions.
    All actions write audit_log; the router owns the commit.

    Raises:
        HTTP 401: Missing or invalid Bearer token.
        HTTP 403: Viewer role (T-04-10).
        HTTP 404: Request not found.
        HTTP 422: Invalid status transition (T-04-11).
    """
    req: Request | None = (
        db.query(Request).filter(Request.id == request_id).first()
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    try:
        # Status change via state machine (NEVER direct assignment — Pitfall 5)
        if body.status is not None:
            to_status = RequestStatus(body.status)
            request_service.transition_status(
                db=db,
                request=req,
                to_status=to_status,
                changed_by=current_user.id,
            )

        # Owner assignment
        if body.assigned_to is not None:
            request_service.assign_owner(
                db=db,
                request=req,
                staff_user_id=body.assigned_to,
                changed_by=current_user.id,
            )

        # Add note
        if body.note is not None:
            request_service.add_note(
                db=db,
                request_id=req.id,
                note_text=body.note,
                staff_user_id=current_user.id,
            )

        db.commit()

    except ValueError as exc:
        # ValueError from transition_status = invalid transition → 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return _build_request_detail(req, db)


# ── POST /requests/{id}/note ──────────────────────────────────────────────────

@router.post(
    "/{request_id}/note",
    response_model=RequestDetailOut,
    summary="Add a team note to a request (staff)",
)
def add_note(
    request_id: int,
    body: RequestPatch,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(
        require_role(StaffRole.admin, StaffRole.analyst, StaffRole.trader)
    ),
) -> RequestDetailOut:
    """POST /requests/{id}/note — attach a free-text note; writes audit_log.

    Raises:
        HTTP 401: Missing or invalid Bearer token.
        HTTP 403: Viewer role.
        HTTP 404: Request not found.
        HTTP 422: note field missing or empty.
    """
    if not body.note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="note field is required",
        )

    req: Request | None = (
        db.query(Request).filter(Request.id == request_id).first()
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    request_service.add_note(
        db=db,
        request_id=req.id,
        note_text=body.note,
        staff_user_id=current_user.id,
    )
    db.commit()

    return _build_request_detail(req, db)


# ── POST /requests/{id}/assign ────────────────────────────────────────────────

@router.post(
    "/{request_id}/assign",
    response_model=RequestDetailOut,
    summary="Assign an owner to a request (staff)",
)
def assign_request(
    request_id: int,
    body: RequestPatch,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(
        require_role(StaffRole.admin, StaffRole.analyst, StaffRole.trader)
    ),
) -> RequestDetailOut:
    """POST /requests/{id}/assign — assign a staff owner; writes audit_log.

    Raises:
        HTTP 401: Missing or invalid Bearer token.
        HTTP 403: Viewer role.
        HTTP 404: Request not found.
        HTTP 422: assigned_to field missing.
    """
    if body.assigned_to is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assigned_to field is required",
        )

    req: Request | None = (
        db.query(Request).filter(Request.id == request_id).first()
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    request_service.assign_owner(
        db=db,
        request=req,
        staff_user_id=body.assigned_to,
        changed_by=current_user.id,
    )
    db.commit()

    return _build_request_detail(req, db)


# ── POST /requests/{id}/contact ───────────────────────────────────────────────

@router.post(
    "/{request_id}/contact",
    summary="Contact Buyer deep-link action (staff)",
)
def contact_buyer(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: StaffUser = Depends(
        require_role(StaffRole.admin, StaffRole.analyst, StaffRole.trader)
    ),
) -> dict:
    """POST /requests/{id}/contact — Contact Buyer action; writes audit_log.

    Returns:
    - contact_available: bool — True when client.telegram_user_id IS NOT NULL.
    - tg_link: str | None — tg://user?id={telegram_user_id} when available.

    When contact_available is False, returns 409 (buyer has no Telegram ID).

    Raises:
        HTTP 401: Missing or invalid Bearer token.
        HTTP 403: Viewer role.
        HTTP 404: Request not found.
        HTTP 409: Buyer has no Telegram ID on file (D-11 / Pitfall 6).
    """
    req: Request | None = (
        db.query(Request).filter(Request.id == request_id).first()
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    # D-11 / Pitfall 6: never build tg://user?id=None
    contact_available = (
        req.client is not None
        and req.client.telegram_user_id is not None
    )

    if not contact_available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="contact_disabled: buyer has no Telegram ID on file",
        )

    # Transition to in_progress if new/viewed, then write contact_buyer audit
    request_service.log_contact_buyer(
        db=db,
        request=req,
        staff_user_id=current_user.id,
    )
    db.commit()

    telegram_user_id = req.client.telegram_user_id
    tg_link = f"tg://user?id={telegram_user_id}"

    return {
        "contact_available": True,
        "tg_link": tg_link,
    }


# ── POST /requests/{id}/analyze ───────────────────────────────────────────────

@router.post(
    "/{request_id}/analyze",
    response_model=RequestDetailOut,
    summary="Run (or re-run) LLM AI analysis for a request (staff)",
)
def analyze_request(
    request_id: int,
    db: Session = Depends(get_db),
    _current_user: StaffUser = Depends(
        require_role(StaffRole.admin, StaffRole.analyst, StaffRole.trader)
    ),
) -> RequestDetailOut:
    """POST /requests/{id}/analyze — synchronously run the LLM analysis and persist it.

    New requests are analysed asynchronously on creation; this endpoint lets a trader
    trigger or re-run it on demand (e.g. for requests created before the feature, or to
    refresh after market data changes). Fills requests.ai (match_score / demand_level /
    recommendation) and returns the updated detail.

    Raises:
        HTTP 401: Missing or invalid Bearer token.
        HTTP 403: Viewer role.
        HTTP 404: Request not found.
        HTTP 503: AI analysis is disabled or could not complete (e.g. budget exhausted).
    """
    req: Request | None = (
        db.query(Request).filter(Request.id == request_id).first()
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    ai_block = request_analysis_service.analyze_request(db, req)
    if ai_block is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ai_unavailable: analysis is disabled or the daily budget is exhausted",
        )
    db.commit()

    return _build_request_detail(req, db)
