"""Admin: load the Central Bank's bank-branch register.

GET  /admin/bank-register   — what is live now (file, its date, row count, who)
POST /admin/bank-register   — upload a new .xlsx; replaces the table

Its own router rather than a route on the products one, because that router
carries a router-level `require_page("adminProducts", …)` and this is a different
page with a different grant.

The register is republished by the CB periodically. Before this existed, refreshing
it would have meant editing code and deploying; the whole point is that an operator
can drop in the new file.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_page
from app.core.db import get_db
from app.domains.reference import bank_service
from app.domains.reference.schemas import BankRegisterImportOut, BankRegisterStatusOut
from app.models.staff import StaffUser

router = APIRouter(prefix="/admin/bank-register", tags=["admin-bank-register"])


@router.get(
    "",
    response_model=BankRegisterStatusOut,
    summary="The bank register currently loaded",
)
def register_status(
    db: Session = Depends(get_db),
    _user: StaffUser = Depends(require_page("adminBankRegister", "read")),
) -> BankRegisterStatusOut:
    """GET /admin/bank-register — provenance of the live register.

    `loaded=false` on a deployment where the seeder has not run; the screen says
    so rather than showing a confident zero, because "no register" and "a register
    with no banks" are different problems.
    """
    record = bank_service.current_import(db)
    if record is None:
        return BankRegisterStatusOut(loaded=False, row_count=0)
    staff = db.get(StaffUser, record.uploaded_by) if record.uploaded_by else None
    return BankRegisterStatusOut(
        loaded=True,
        row_count=bank_service.count(db),
        filename=record.filename,
        file_created_at=record.file_created_at,
        uploaded_at=record.created_at,
        # None means the copy that shipped with the release, which is a fact worth
        # showing: nobody on this deployment has replaced it.
        uploaded_by=(staff.email if staff else None),
    )


@router.post(
    "",
    response_model=BankRegisterImportOut,
    summary="Upload a new bank register (.xlsx)",
)
def upload_register(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: StaffUser = Depends(require_page("adminBankRegister", "write")),
) -> BankRegisterImportOut:
    """POST /admin/bank-register — replace the register from the CB's .xlsx.

    Sync `def` on purpose, like every other upload handler here: the body reads
    `file.file` (the underlying SpooledTemporaryFile) and then does DB work, and
    as `async def` that runs on the event loop and stalls every other request.

    The parse happens before anything is deleted, so a wrong file is refused with
    422 and the working register is still there — see `bank_service`.
    """
    content = file.file.read()
    try:
        outcome = bank_service.import_register(
            db, content, file.filename or "upload.xlsx", staff_user_id=user.id
        )
    except ValueError as exc:  # BankRegisterInvalid is a ValueError
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    return BankRegisterImportOut(
        imported=outcome.imported,
        row_count=outcome.row_count,
        file_created_at=outcome.file_created_at,
    )
