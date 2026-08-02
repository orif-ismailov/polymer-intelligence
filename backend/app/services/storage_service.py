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

import hashlib
import logging
import os
import secrets

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.companies import Company
from app.models.enums import OfferFileKind, VerificationDocumentKind
from app.models.marketplace import SellerOfferFile
from app.models.media import CompanyMedia
from app.models.requests import RequestFile
from app.models.verification import VerificationDocument

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
    b"\x89PNG\r\n\x1a\n": "image/png",
}

#: Verification documents accept a stricter set than request/offer uploads
#: (no spreadsheets): PDF scans + JPEG/PNG photos of certificates.
VERIFICATION_MIMES: frozenset[str] = frozenset(
    {"application/pdf", "image/jpeg", "image/png"}
)

#: Maximum verification documents per company (abuse bound).
MAX_VERIFICATION_DOCS: int = 20

#: Maximum allowed file size in bytes (10 MB, per D-08).
MAX_SIZE_BYTES: int = 10 * 1024 * 1024

#: Maximum number of files per request (D-08). Enforced by the router before
#: calling upload_request_file; exposed here as the authoritative constant.
MAX_FILES: int = 5

#: Maximum number of files (images + docs) per seller offer (Phase 2 marketplace).
MAX_OFFER_FILES: int = 10

#: Maximum PHOTOS per offer (FR-M2). Counted over kind='image' only, so a TDS or
#: certificate never consumes a photo slot. Independent of MAX_OFFER_FILES.
MAX_OFFER_IMAGES: int = 8

#: `kind='image'` must actually be an image — the generic allow-list also permits
#: PDFs and spreadsheets, which are fine as documents but not as product photos.
IMAGE_MIMES: frozenset[str] = frozenset({"image/jpeg", "image/png"})

#: A company logo is a picture, never a document — stricter than VERIFICATION_MIMES.
LOGO_MIMES: frozenset[str] = frozenset({"image/jpeg", "image/png"})

#: Logos are small by nature; 5 MB (FR-M1) rather than the generic 10 MB.
MAX_LOGO_SIZE_BYTES: int = 5 * 1024 * 1024

#: Object-key extension per accepted logo MIME.
_LOGO_EXTENSIONS: dict[str, str] = {"image/jpeg": "jpg", "image/png": "png"}


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


def upload_offer_file(
    db: Session,
    offer_id: int,
    content: bytes,
    filename: str,
    kind: OfferFileKind,
) -> SellerOfferFile:
    """Validate content, stream to MinIO, insert a seller_offer_files row.

    Same traversal-safe key pattern as upload_request_file (offers/{offer_id}/…) and
    the same magic-byte/size validation. Does NOT commit — caller commits.
    """
    from app.core.storage import s3_client  # noqa: PLC0415 — deferred to avoid socket at import

    mime = validate_upload(content, filename)

    sanitized_basename = os.path.basename(filename) or "upload"
    sanitized_basename = sanitized_basename.replace("/", "_").replace("\\", "_").replace("..", "__")
    random_token = secrets.token_hex(8)
    key = f"offers/{offer_id}/{random_token}-{sanitized_basename}"

    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=mime,
    )

    f = SellerOfferFile(
        offer_id=offer_id,
        kind=kind,
        file_name=os.path.basename(filename) or "upload",
        mime_type=mime,
        size_bytes=len(content),
        storage_path=key,
    )
    db.add(f)
    db.flush()
    logger.info(
        "storage_service.upload_offer_file.done",
        extra={"offer_id": offer_id, "key": key, "mime": mime, "kind": kind.value},
    )
    return f


# ── Company logo (P1 W1 — T1.2) ───────────────────────────────────────────────


def discard_object(key: str, *, context: str) -> None:
    """Best-effort S3 delete.

    Deliberately fail-soft: a leftover object costs storage, but letting the error
    escape would fail the user's upload (or leave `logo_storage_path` pointing at a
    logo they asked us to remove). Logged so the leak is visible.
    """
    from app.core.storage import s3_client  # noqa: PLC0415 — deferred (no socket at import)

    try:
        s3_client.delete_object(Bucket=settings.S3_BUCKET, Key=key)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — cleanup must never break the caller
        logger.warning("storage_service.discard_object.failed", extra={"key": key, "ctx": context})


def upload_company_logo(
    db: Session,
    company: Company,
    content: bytes,
    filename: str,
) -> str:
    """Validate + store a company logo, returning the new object key.

    Stricter than the generic upload: JPEG/PNG only and 5 MB (FR-M1). The key is
    built from a random token and the detected MIME, so the client's filename never
    reaches the object store at all. Replacing a logo deletes the previous object
    (fail-soft). Sets `company.logo_storage_path`; does NOT commit — caller commits.
    """
    from app.core.storage import s3_client  # noqa: PLC0415 — deferred (no socket at import)

    if len(content) > MAX_LOGO_SIZE_BYTES:
        logger.debug(
            "storage_service.upload_company_logo.too_large",
            extra={"size": len(content), "limit": MAX_LOGO_SIZE_BYTES},
        )
        raise ValueError("file_too_large")

    # validate_upload also enforces the generic 10 MB cap; the 5 MB check above
    # runs first so an oversized logo reports the limit that actually applies.
    mime = validate_upload(content, filename)
    if mime not in LOGO_MIMES:
        logger.debug("storage_service.upload_company_logo.bad_mime", extra={"mime": mime})
        raise ValueError("invalid_file_type")

    previous_key = company.logo_storage_path
    key = f"companies/{company.id}/logo/{secrets.token_hex(8)}.{_LOGO_EXTENSIONS[mime]}"

    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=mime,
    )
    company.logo_storage_path = key
    db.flush()

    if previous_key and previous_key != key:
        discard_object(previous_key, context="logo_replace")

    logger.info(
        "storage_service.upload_company_logo.done",
        extra={"company_id": company.id, "key": key, "mime": mime, "replaced": bool(previous_key)},
    )
    return key


def delete_company_logo(db: Session, company: Company) -> None:
    """Remove the company logo. No-op when there isn't one (idempotent)."""
    key = company.logo_storage_path
    if not key:
        return

    company.logo_storage_path = None
    db.flush()
    discard_object(key, context="logo_delete")
    logger.info(
        "storage_service.delete_company_logo.done",
        extra={"company_id": company.id, "key": key},
    )


# ── Verification document vault (R1 W4 — T4.3) ────────────────────────────────


def upload_verification_document(
    db: Session,
    company: Company,
    account_id: int,
    kind: VerificationDocumentKind,
    content: bytes,
    filename: str,
) -> VerificationDocument:
    """Validate + store one verification document (PDF/JPEG/PNG, ≤10 MB, ≤20/company).

    Immutable evidence: the sha256 of the bytes is stored so tampering is detectable.
    Traversal-safe key `verification/{company_id}/{token}-{basename}`. Does NOT commit.
    """
    mime = validate_upload(content, filename)  # size + magic bytes
    if mime not in VERIFICATION_MIMES:
        raise ValueError("invalid_file_type")

    existing = (
        db.query(VerificationDocument)
        .filter(VerificationDocument.company_id == company.id)
        .count()
    )
    if existing >= MAX_VERIFICATION_DOCS:
        raise ValueError("too_many_documents")

    from app.core.storage import s3_client  # noqa: PLC0415 — deferred (no socket at import)

    sanitized_basename = os.path.basename(filename) or "upload"
    sanitized_basename = (
        sanitized_basename.replace("/", "_").replace("\\", "_").replace("..", "__")
    )
    key = f"verification/{company.id}/{secrets.token_hex(8)}-{sanitized_basename}"

    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET, Key=key, Body=content, ContentType=mime
    )

    document = VerificationDocument(
        company_id=company.id,
        kind=kind,
        storage_path=key,
        mime_type=mime,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by_user_account_id=account_id,
    )
    db.add(document)
    db.flush()
    logger.info(
        "storage_service.upload_verification_document.done",
        extra={"company_id": company.id, "key": key, "mime": mime, "kind": kind.value},
    )
    return document


def presign_company_logo(company: Company, ttl: int = 600) -> str | None:
    """URL a browser can actually load for a company logo, or None if it has none.

    NOT a presigned S3 link. `S3_ENDPOINT` is the INTERNAL address of the object
    store (`http://minio:9000` under compose), so a presigned URL is signed against
    a host no browser can resolve — every `<img src>` built from one renders as a
    broken image. The bytes are therefore served by the API itself
    (`GET /webapp/market/companies/{id}/logo`), the same proxy pattern offer photos
    already use, which also keeps media same-origin with the portal.

    Returned as a root-relative path so it works unchanged behind every host the
    app is served from (cabinet./dev-cabinet./localhost) with no base-URL config.

    `ttl` is accepted for call-site compatibility and ignored: the proxy route
    carries no signature to expire.
    """
    if not company.logo_storage_path:
        return None
    return f"/api/v1/webapp/market/companies/{company.id}/logo"


def presign_verification_document(document: VerificationDocument, ttl: int = 600) -> str:
    """Return a short-lived presigned GET URL for a verification document (≤600 s)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    url = s3_client.generate_presigned_url(  # type: ignore[attr-defined]
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": document.storage_path},
        ExpiresIn=ttl,
    )
    return str(url)


# ── E-IMZO signature evidence (R3 TA1.4) ──────────────────────────────────────


def store_eimzo_pkcs7(company_id: int, pkcs7_bytes: bytes) -> tuple[str, str]:
    """Store a PKCS#7 blob as immutable evidence; return (storage_path, sha256).

    Key `evidence/eimzo/{company_id}/{token}.p7s` (traversal-safe by construction —
    no user-supplied filename). The sha256 is returned so the caller can persist it
    on the signature_evidence row for later tamper detection. Does NOT write a DB row.
    """
    from app.core.storage import s3_client  # noqa: PLC0415

    key = f"evidence/eimzo/{company_id}/{secrets.token_hex(8)}.p7s"
    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=pkcs7_bytes,
        ContentType="application/pkcs7-signature",
    )
    return key, hashlib.sha256(pkcs7_bytes).hexdigest()


def presign_eimzo_pkcs7(storage_path: str, ttl: int = 600) -> str:
    """Presigned GET URL for a stored PKCS#7 evidence blob (≤600 s)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    url = s3_client.generate_presigned_url(  # type: ignore[attr-defined]
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": storage_path},
        ExpiresIn=ttl,
    )
    return str(url)


# ── Contracts (R3 Stage B) ────────────────────────────────────────────────────


def store_contract_template(code: str, version: int, html: str) -> str:
    """Upload a contract template body to S3; return its key (idempotent overwrite)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    key = f"contracts/templates/{code}_v{version}.html"
    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET, Key=key, Body=html.encode("utf-8"), ContentType="text/html"
    )
    return key


def get_object_text(key: str) -> str:
    """Fetch an S3 object and decode it as UTF-8 text (contract template bodies)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    obj = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=key)  # type: ignore[attr-defined]
    return str(obj["Body"].read().decode("utf-8"))


def store_contract_pdf(contract_public_id: str, version_n: int, pdf_bytes: bytes) -> tuple[str, str]:
    """Store a rendered contract PDF; return (storage_path, sha256)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    key = f"contracts/{contract_public_id}/contract_v{version_n}.pdf"
    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET, Key=key, Body=pdf_bytes, ContentType="application/pdf"
    )
    return key, hashlib.sha256(pdf_bytes).hexdigest()


# ── Deal room files (P2 W1 — T1.2) ────────────────────────────────────────────

#: Attachments in a Trade Room: contracts and invoices (PDF), price sheets
#: (XLSX), photos of documents or cargo (JPEG/PNG). Named explicitly rather than
#: reusing ALLOWED_MIMES, which omits PNG even though validate_upload detects it.
DEAL_FILE_MIMES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "image/png",
    }
)


def store_deal_file(
    deal_id: int, section: str, content: bytes, filename: str
) -> tuple[str, str, str]:
    """Validate + store a Trade Room attachment; return (key, mime, sha256).

    `section` is 'chat' or 'documents' — a fixed caller-supplied literal, never
    user input, so it cannot escape the deal's prefix. The client's filename is
    sanitized into the key exactly as for request/offer uploads (traversal-safe)
    and kept separately for display.

    Validation happens BEFORE the write, so a rejected file leaves nothing
    behind in the bucket.
    """
    from app.core.storage import s3_client  # noqa: PLC0415 — deferred (no socket at import)

    mime = validate_upload(content, filename)
    if mime not in DEAL_FILE_MIMES:
        logger.debug("storage_service.store_deal_file.bad_mime", extra={"mime": mime})
        raise ValueError("invalid_file_type")

    basename = os.path.basename(filename) or "upload"
    safe = basename.replace("/", "_").replace("\\", "_").replace("..", "__")
    key = f"deals/{deal_id}/{section}/{secrets.token_hex(8)}-{safe}"

    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=mime,
    )
    logger.info(
        "storage_service.store_deal_file.done",
        extra={"deal_id": deal_id, "section": section, "key": key, "mime": mime},
    )
    return key, mime, hashlib.sha256(content).hexdigest()


def store_factory_rfq_file(
    rfq_id: int, content: bytes, filename: str
) -> tuple[str, str]:
    """Validate + store a factory-RFQ compliance document; return (key, mime)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    mime = validate_upload(content, filename)
    if mime not in DEAL_FILE_MIMES:
        raise ValueError("invalid_file_type")

    basename = os.path.basename(filename) or "upload"
    safe = basename.replace("/", "_").replace("\\", "_").replace("..", "__")
    key = f"factory-rfqs/{rfq_id}/{secrets.token_hex(8)}-{safe}"

    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=mime,
    )
    return key, mime


def store_manufacturer_chat_file(
    thread_id: int, content: bytes, filename: str
) -> tuple[str, str]:
    """Validate + store a manufacturer-thread chat attachment; return (key, mime)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    mime = validate_upload(content, filename)
    if mime not in DEAL_FILE_MIMES:
        raise ValueError("invalid_file_type")

    basename = os.path.basename(filename) or "upload"
    safe = basename.replace("/", "_").replace("\\", "_").replace("..", "__")
    key = f"manufacturer-chat/{thread_id}/{secrets.token_hex(8)}-{safe}"

    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=mime,
    )
    return key, mime


def get_object_bytes(key: str) -> bytes:
    """Fetch an S3 object's raw bytes (contract PDF integrity checks)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    obj = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=key)  # type: ignore[attr-defined]
    return bytes(obj["Body"].read())


def presign_object(key: str, ttl: int = 600) -> str:
    """Generic short-lived presigned GET URL for any stored object (≤600 s)."""
    from app.core.storage import s3_client  # noqa: PLC0415

    url = s3_client.generate_presigned_url(  # type: ignore[attr-defined]
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=ttl,
    )
    return str(url)


# ── State-registry evidence (R6 / P7.c) ───────────────────────────────────────

#: An operator's registry screenshot is a picture or a saved PDF page — never a
#: spreadsheet. Narrower than VERIFICATION_MIMES on purpose.
REGISTRY_EVIDENCE_MIMES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "application/pdf"}
)


def store_registry_evidence(
    company_id: int, content: bytes, filename: str
) -> tuple[str, str]:
    """Store an operator's registry screenshot; return (storage_path, sha256).

    Same treatment as a PKCS#7 in `store_eimzo_pkcs7`: immutable object, hash
    returned so the snapshot row can carry it and tampering stays detectable.
    Key `evidence/registry/{company_id}/{token}.{ext}` — traversal-safe by
    construction, since the extension comes from the detected MIME and never from
    the client's filename.

    Raises ValueError('file_too_large' | 'invalid_file_type') — the caller refuses
    the whole request rather than recording a snapshot that claims evidence it
    does not have.
    """
    from app.core.storage import s3_client  # noqa: PLC0415

    mime = validate_upload(content, filename)  # size + magic bytes
    if mime not in REGISTRY_EVIDENCE_MIMES:
        raise ValueError("invalid_file_type")

    extension = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}[mime]
    key = f"evidence/registry/{company_id}/{secrets.token_hex(8)}.{extension}"
    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET, Key=key, Body=content, ContentType=mime
    )
    logger.info(
        "storage_service.store_registry_evidence.done",
        extra={"company_id": company_id, "key": key, "mime": mime},
    )
    return key, hashlib.sha256(content).hexdigest()


# ── Company cover + media (P6) ────────────────────────────────────────────────

#: Hero images are wider than a logo and carry photographic detail, so the 5 MB
#: logo cap is too tight; the generic 10 MB `validate_upload` ceiling applies.
MAX_COVER_SIZE_BYTES = 8 * 1024 * 1024


def _store_image(company_id: int, folder: str, content: bytes, filename: str) -> tuple[str, str]:
    """Validate an image and put it in the bucket. Returns `(key, mime)`.

    Shared by the cover and the capability thumbnails so there is one place that
    decides what an image is: JPEG/PNG only, and the key built from a random
    token plus the DETECTED mime, so the client's filename never reaches the
    object store.
    """
    from app.core.storage import s3_client  # noqa: PLC0415 — deferred (no socket at import)

    mime = validate_upload(content, filename)
    if mime not in LOGO_MIMES:
        logger.debug("storage_service._store_image.bad_mime", extra={"mime": mime})
        raise ValueError("invalid_file_type")

    key = f"companies/{company_id}/{folder}/{secrets.token_hex(8)}.{_LOGO_EXTENSIONS[mime]}"
    s3_client.put_object(  # type: ignore[attr-defined]
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=mime,
    )
    return key, mime


def upload_company_cover(
    db: Session, company: Company, content: bytes, filename: str
) -> str:
    """Store a company cover image, replacing any previous one. Flush-only."""
    if len(content) > MAX_COVER_SIZE_BYTES:
        raise ValueError("file_too_large")

    previous_key = company.cover_storage_path
    key, mime = _store_image(company.id, "cover", content, filename)
    company.cover_storage_path = key
    db.flush()

    # The same cleanup `upload_company_logo` does and `add_factory_rfq_document`
    # forgets — a replaced cover would otherwise leak an object per edit.
    if previous_key and previous_key != key:
        discard_object(previous_key, context="cover_replace")

    logger.info(
        "storage_service.upload_company_cover.done",
        extra={"company_id": company.id, "key": key, "mime": mime},
    )
    return key


def delete_company_cover(db: Session, company: Company) -> None:
    """Remove the cover. No-op when there isn't one (idempotent)."""
    key = company.cover_storage_path
    if not key:
        return
    company.cover_storage_path = None
    db.flush()
    discard_object(key, context="cover_delete")


def presign_company_cover(company: Company, ttl: int = 600) -> str | None:
    """Root-relative path to the cover bytes, or None.

    Not a presigned S3 URL, for the reason spelled out on `presign_company_logo`:
    `S3_ENDPOINT` is the internal address, so a signed link is a broken `<img>`.
    """
    if not company.cover_storage_path:
        return None
    return f"/api/v1/webapp/market/companies/{company.id}/cover"


def upload_company_media(
    db: Session, company: Company, content: bytes, filename: str
) -> CompanyMedia:
    """Store one company image and return its row. Flush-only.

    The caller references the returned id from wherever it needs the picture —
    for carriers, `logistics_profile.capability_images[<capability_key>]`.
    """
    if len(content) > MAX_COVER_SIZE_BYTES:
        raise ValueError("file_too_large")

    key, mime = _store_image(company.id, "media", content, filename)
    media = CompanyMedia(
        company_id=company.id,
        storage_path=key,
        mime_type=mime,
        size_bytes=len(content),
    )
    db.add(media)
    db.flush()
    logger.info(
        "storage_service.upload_company_media.done",
        extra={"company_id": company.id, "media_id": media.id},
    )
    return media


def company_media_url(company_id: int, media_id: int) -> str:
    """Root-relative path to a media object's bytes.

    The COMPANY id is in the path as well as the media id so the serving route
    can require the two to match — otherwise the id alone would be a handle to
    every image in the bucket.
    """
    return f"/api/v1/webapp/market/companies/{company_id}/media/{media_id}"
