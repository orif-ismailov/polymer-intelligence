"""
/webapp/requests/{id}/files — multipart file upload to MinIO.

Authentication and ownership enforced per request:
  - get_current_client dep verifies initData HMAC + upserts client
  - Request row is fetched scoped to client.id (T-03-07 IDOR guard)
  - File limits enforced before MinIO write (T-03-04/T-03-05)

Security:
  T-03-04: MIME detection by magic bytes (not extension) via storage_service.validate_upload
  T-03-05: Max 10 MB per file + max 5 files per request enforced before any S3 write
  T-03-07: IDOR — request must be owned by the calling client; cross-client → 404
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_client
from app.core.db import get_db
from app.domains.requests.models import Client, Request, RequestFile
from app.domains.requests.webapp_schemas import RequestFileOut
from app.services import storage_service
from app.services.storage_service import MAX_FILES

router = APIRouter(prefix="/webapp", tags=["webapp"])


@router.post(
    "/requests/{request_id}/files",
    response_model=RequestFileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file to a client purchase request",
)
async def upload_request_file(
    request_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> RequestFileOut:
    """POST /webapp/requests/{id}/files — upload PDF/Excel/JPG ≤10 MB to MinIO.

    Ownership check:
      Fetches the Request by id AND client_id (from dep, never body).
      If not found or not owned by caller → 404 (T-03-07).

    File limit:
      Enforces MAX_FILES=5 before attempting upload.
      6th file → 422 too_many_files (T-03-05).

    Content validation:
      storage_service.upload_request_file validates magic bytes + size.
      ValueError("file_too_large") → 422; ValueError("invalid_file_type") → 422.

    Raises:
        HTTP 401: missing or invalid X-Telegram-Init-Data.
        HTTP 404: request not found or not owned by the calling client (T-03-07).
        HTTP 422: too_many_files | file_too_large | invalid_file_type.
    """
    # T-03-07: ownership check — scope by client.id from dep, never body
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

    # T-03-05: enforce MAX_FILES limit before any S3 write
    existing_count: int = (
        db.query(RequestFile)
        .filter(RequestFile.request_id == request_id)
        .count()
    )
    if existing_count >= MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="too_many_files",
        )

    # Read the file content (enforce 10 MB limit inside validate_upload)
    content: bytes = await file.read()

    try:
        rf = storage_service.upload_request_file(
            db=db,
            request_id=request_id,
            content=content,
            filename=file.filename or "upload",
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return RequestFileOut(
        id=rf.id,
        file_name=rf.file_name,
        mime_type=rf.mime_type,
        size_bytes=rf.size_bytes,
    )


@router.get(
    "/requests/{request_id}/files/{file_id}",
    summary="Stream/download a request file (owner-only)",
)
def get_request_file(
    request_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> Response:
    """GET /webapp/requests/{id}/files/{file_id} — the file's bytes, inline.

    Owner-scoped (T-03-07): the request must belong to the calling client, else 404.
    Returns the stored bytes with the original mime type so the client can render
    images inline or open/download other types.
    """
    req: Request | None = (
        db.query(Request)
        .filter(Request.id == request_id, Request.client_id == client.id)
        .first()
    )
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    f: RequestFile | None = (
        db.query(RequestFile)
        .filter(RequestFile.id == file_id, RequestFile.request_id == request_id)
        .first()
    )
    if f is None or f.storage_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    from app.core.config import settings  # noqa: PLC0415
    from app.core.storage import s3_client  # noqa: PLC0415

    obj = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=f.storage_path)  # type: ignore[attr-defined]
    body: bytes = obj["Body"].read()
    return Response(
        content=body,
        media_type=f.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{f.file_name}"'},
    )
