"""Staff view of the Didox rail (P7.a Stage 2 — W10). Read-only, under /api/v1.

Two things staff need and cannot get anywhere else:

  * **which documents need a human** — status `4` (a counterparty refused) and
    `50` (annulled by the tax committee) are recorded and alerted but never acted
    on, so they need a queue rather than a Telegram message that scrolls away;
  * **which companies are stuck in onboarding** — a company with an unsigned
    public offer looks fine everywhere else and then fails its first send.

Read-only on purpose. Everything here is either the provider's fact or a legal
event; there is no staff action that could be correct.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_analyst_or_admin
from app.core.db import get_db
from app.domains.edi import onboarding
from app.domains.edi.models import DidoxCompany, DidoxDocument
from app.domains.edi.schemas import DidoxAdminCompanyOut, DidoxAdminDocumentOut
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin/didox", tags=["admin-didox"])

#: Recorded, alerted, and never auto-applied — see `edi_service.apply_status`.
NEEDS_ATTENTION = (4, 50)


@router.get("/documents", response_model=list[DidoxAdminDocumentOut])
def list_documents(
    status: int | None = Query(default=None, description="Didox status, verbatim"),
    attention: bool = Query(default=False, description="Only 4 (rejected) / 50 (annulled)"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: StaffUser = Depends(require_analyst_or_admin),
) -> list[DidoxAdminDocumentOut]:
    query = db.query(DidoxDocument)
    if attention:
        query = query.filter(DidoxDocument.status.in_(NEEDS_ATTENTION))
    elif status is not None:
        query = query.filter(DidoxDocument.status == status)
    rows = query.order_by(DidoxDocument.id.desc()).limit(limit).all()
    return [
        DidoxAdminDocumentOut(
            id=row.id,
            doc_type=row.doc_type,
            number=row.number,
            status=row.status,
            didox_id=row.didox_id,
            subject_kind=row.subject_kind,
            subject_id=row.subject_id,
            deal_id=row.deal_id,
            owner_company_id=row.owner_company_id,
            archived=row.provider_archive_sha256 is not None,
            status_synced_at=row.status_synced_at,
            last_error=row.last_error,
        )
        for row in rows
    ]


@router.get("/companies", response_model=list[DidoxAdminCompanyOut])
def list_companies(
    stuck: bool = Query(default=False, description="Only companies not yet `ready`"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: StaffUser = Depends(require_analyst_or_admin),
) -> list[DidoxAdminCompanyOut]:
    """Onboarding state per company — the queue for "cannot send yet"."""
    rows = db.query(DidoxCompany).order_by(DidoxCompany.company_id).limit(limit).all()
    out = [
        DidoxAdminCompanyOut(
            company_id=row.company_id,
            tin=row.tin,
            state=onboarding.state_of(row),
            signup_at=row.signup_at,
            offer_signed_at=row.offer_signed_at,
            last_polled_at=row.last_polled_at,
            last_error=row.last_error,
        )
        for row in rows
    ]
    return [row for row in out if row.state != onboarding.READY] if stuck else out
