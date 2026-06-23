"""
Storage service — file upload validation and MinIO write for client request files.

Upload pipeline (D-07, dev-spec §4.2):
  1. validate_upload: magic-byte MIME check + size check — rejects before any S3 write.
  2. upload_request_file: validates, builds a traversal-safe S3 key, writes to MinIO,
     inserts a request_files row (no commit — caller commits).

Security invariants:
  T-03-04: MIME is determined by magic bytes, NOT file extension. A .pdf with ELF
           header is rejected. Extension is only used for the sanitized filename
           component in the S3 key (cosmetic), not for type detection.
  T-03-05: Max 10 MB per file enforced in validate_upload (MAX_SIZE_BYTES). Max 5
           files per request enforced by the caller via MAX_FILES (counted by the
           router before calling upload_request_file).
  T-03-06: S3 key is built from a random token + sanitized basename. Raw user
           filename is never used as-is in the key. Directory components ('..', '/')
           are stripped before the basename is embedded. This closes the path-
           traversal attack vector on the object store.

D-09 note: telegram_file_id is left NULL for Web App uploads — that column is the
fallback for files sent directly to the bot (which carry a file_id from Telegram's
CDN). Web App uploads always go to MinIO via this pipeline, never via Telegram CDN.
"""

from __future__ import annotations

import logging
import os
import secrets

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.requests import RequestFile

logger = logging.getLogger(__name__)

# ── Upload limits (D-08 authoritative server-side values) ──────────────────────

#: Allowed MIME types mapped from magic-byte prefixes.
ALLOWED_MIMES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
}

#: Magic-byte prefix → MIME mapping. Checked in order; first match wins.
#: Key length determines how many bytes are read from the start of content.
MAGIC_BYTES: dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    b"\xff\xd8\xff": "image/jpeg",
}

#: Maximum allowed file size in bytes (10 MB, per D-08).
MAX_SIZE_BYTES: int = 10 * 1024 * 1024

#: Maximum number of files per request (D-08). Enforced by the router before
#: calling upload_request_file; exposed here as the authoritative constant.
MAX_FILES: int = 5


# ── Core validation ────────────────────────────────────────────────────────────

def validate_upload(content: bytes, filename: str) -> str:
    """Validate file content by size and magic bytes.  Return the detected MIME type.

    Size is checked FIRST (fast path) so a 1 GB ELF binary fails immediately
    without reading magic bytes.

    Magic bytes are checked against MAGIC_BYTES (NOT extension — T-03-04).

    Args:
        content: Raw bytes of the uploaded file.
        filename: Original filename from the client (used only for logging; NOT
                  used for type detection).

    Returns:
        The detected MIME type string (e.g. "application/pdf").

    Raises:
        ValueError("file_too_large"): when len(content) > MAX_SIZE_BYTES.
        ValueError("invalid_file_type"): when magic bytes do not match any
            entry in MAGIC_BYTES.
    """
    # 1. Size check first (T-03-05)
    if len(content) > MAX_SIZE_BYTES:
        logger.debug(
            "storage_service.validate_upload.too_large",
            extra={"filename": filename, "size": len(content), "limit": MAX_SIZE_BYTES},
        )
        raise ValueError("file_too_large")

    # 2. Magic-byte check (T-03-04 — extension is irrelevant)
    for magic, mime in MAGIC_BYTES.items():
        if content.startswith(magic):
            logger.debug(
                "storage_service.validate_upload.accepted",
                extra={"filename": filename, "mime": mime},
            )
            return mime

    logger.debug(
        "storage_service.validate_upload.invalid_type",
        extra={"filename": filename, "magic_head": content[:8].hex()},
    )
    raise ValueError("invalid_file_type")


# ── Upload helper ──────────────────────────────────────────────────────────────

def upload_request_file(
    db: Session,
    request_id: int,
    content: bytes,
    filename: str,
) -> RequestFile:
    """Validate content, stream to MinIO, insert a request_files row.

    Does NOT commit — caller commits the full transaction (Service Layer pattern).

    S3 key format (T-03-06 traversal-safe):
        requests/{request_id}/{random_hex}-{sanitized_basename}

    The sanitized_basename is derived by:
      - Stripping all directory components (os.path.basename) so '../../etc/passwd'
        becomes 'passwd'.
      - The random token (secrets.token_hex(8)) ensures key uniqueness and makes
        enumeration impractical.
      - The raw user-supplied filename is NEVER used as the S3 key or any prefix
        thereof.

    Args:
        db: The active SQLAlchemy session.
        request_id: The ID of the owning Request row.
        content: Raw file bytes (already read from the HTTP multipart body).
        filename: Original filename from the client (for display in request_files;
                  sanitized before embedding in the S3 key).

    Returns:
        The newly inserted RequestFile ORM object (added to session, not committed).

    Raises:
        ValueError: propagated from validate_upload on type/size violations.
        botocore.exceptions.ClientError: on MinIO write failures.
    """
    from app.core.storage import s3_client  # noqa: PLC0415 — deferred to avoid socket at import

    # 1. Validate first — reject before any S3 write (D-07)
    mime = validate_upload(content, filename)

    # 2. Build a traversal-safe S3 key (T-03-06)
    #    Strip directory components from user-supplied filename
    sanitized_basename = os.path.basename(filename) or "upload"
    # Further strip any remaining path separators (handles Windows-style paths)
    sanitized_basename = sanitized_basename.replace("/", "_").replace("\\", "_").replace("..", "__")
    random_token = secrets.token_hex(8)  # 16 hex chars = 64-bit randomness
    key = f"requests/{request_id}/{random_token}-{sanitized_basename}"

    # 3. Write to MinIO (T-03-04: ContentType from magic bytes, not from client header)
    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=mime,
    )

    # 4. Insert request_files row (D-09: telegram_file_id left NULL for Web App uploads)
    rf = RequestFile(
        request_id=request_id,
        file_name=os.path.basename(filename) or "upload",  # original display name
        mime_type=mime,
        size_bytes=len(content),
        storage_path=key,
        telegram_file_id=None,  # D-09: fallback only for bot-sent files
    )
    db.add(rf)
    db.flush()  # flush to get rf.id — do NOT commit (caller commits)

    logger.info(
        "storage_service.upload_request_file.done",
        extra={
            "request_id": request_id,
            "key": key,
            "mime": mime,
            "size": len(content),
        },
    )
    return rf
